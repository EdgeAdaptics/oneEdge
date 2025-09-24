package mqtt

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

// Publisher maintains an mTLS MQTT client that hot-reloads TLS material on SVID rotation.
type Publisher struct {
	log    *slog.Logger
	broker string
	topic  string
	qos    byte

	mu        sync.Mutex
	tlsConfig *tls.Config
	client    mqtt.Client
	clientID  string
}

// NewPublisher constructs a Publisher for the provided MQTT broker and topic.
func NewPublisher(log *slog.Logger, broker, topic string) *Publisher {
	return &Publisher{
		log:    log,
		broker: broker,
		topic:  topic,
		qos:    1,
	}
}

// Run processes SPIFFE updates and refreshes the MQTT client as needed.
func (p *Publisher) Run(ctx context.Context, updates <-chan *workloadapi.X509Context) error {
	for {
		select {
		case <-ctx.Done():
			p.close()
			return ctx.Err()
		case update := <-updates:
			if update == nil {
				continue
			}
			if err := p.applyUpdate(update); err != nil {
				p.log.Error("failed to apply SVID update", slog.String("err", err.Error()))
			}
		}
	}
}

// Publish transmits payload to the configured topic.
func (p *Publisher) Publish(ctx context.Context, payload []byte) error {
	client := p.snapshotClient()
	if client == nil {
		return errors.New("mqtt client not connected")
	}
	token := client.Publish(p.topic, p.qos, false, payload)
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(50 * time.Millisecond):
			if token.WaitTimeout(0) {
				if token.Error() != nil {
					return token.Error()
				}
				return nil
			}
		}
	}
}

// applyUpdate rebuilds the TLS configuration and reconnects if necessary.
func (p *Publisher) applyUpdate(update *workloadapi.X509Context) error {
	cfg, clientID, err := tlsConfigFromUpdate(update)
	if err != nil {
		return err
	}

	p.mu.Lock()
	defer p.mu.Unlock()

	p.tlsConfig = cfg
	p.clientID = clientID

	if p.client != nil {
		p.log.Info("restarting MQTT client with rotated SVID")
		p.client.Disconnect(250)
		p.client = nil
	}

	return p.connectLocked()
}

func (p *Publisher) connectLocked() error {
	if p.tlsConfig == nil {
		return errors.New("TLS config not ready")
	}

	opts := mqtt.NewClientOptions()
	opts.AddBroker(fmt.Sprintf("ssl://%s", p.broker))
	opts.SetClientID(p.clientID)
	opts.SetCleanSession(true)
	opts.SetTLSConfig(p.tlsConfig)
	opts.SetConnectRetry(true)
	opts.SetConnectRetryInterval(5 * time.Second)
	opts.SetConnectTimeout(5 * time.Second)
	opts.SetAutoReconnect(true)
	opts.SetOnConnectHandler(func(c mqtt.Client) {
		p.log.Info("connected to MQTT broker", slog.String("broker", p.broker), slog.String("client_id", p.clientID))
	})
	opts.SetConnectionLostHandler(func(c mqtt.Client, err error) {
		if err != nil {
			p.log.Warn("mqtt connection lost", slog.String("err", err.Error()))
		}
	})

	client := mqtt.NewClient(opts)
	token := client.Connect()
	if !token.WaitTimeout(10 * time.Second) {
		return errors.New("timeout connecting to mqtt broker")
	}
	if err := token.Error(); err != nil {
		return fmt.Errorf("connect mqtt broker: %w", err)
	}

	p.client = client
	return nil
}

func (p *Publisher) snapshotClient() mqtt.Client {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.client
}

func (p *Publisher) close() {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.client != nil {
		p.client.Disconnect(250)
		p.client = nil
	}
}

func tlsConfigFromUpdate(update *workloadapi.X509Context) (*tls.Config, string, error) {
	svid := update.DefaultSVID()
	if svid == nil {
		return nil, "", errors.New("update missing default SVID")
	}

	cert := tls.Certificate{
		PrivateKey:  svid.PrivateKey,
		Leaf:        svid.Certificates[0],
		Certificate: make([][]byte, len(svid.Certificates)),
	}
	for i, c := range svid.Certificates {
		cert.Certificate[i] = c.Raw
	}

	roots := x509.NewCertPool()
	for _, bundle := range update.Bundles.Bundles() {
		for _, ca := range bundle.X509Authorities() {
			roots.AddCert(ca)
		}
	}

	trustDomain := svid.ID.TrustDomain()

	tlsCfg := &tls.Config{
		Certificates:       []tls.Certificate{cert},
		RootCAs:            roots,
		MinVersion:         tls.VersionTLS12,
		InsecureSkipVerify: true,
	}

	tlsCfg.VerifyPeerCertificate = func(rawCerts [][]byte, _ [][]*x509.Certificate) error {
		for _, raw := range rawCerts {
			cert, err := x509.ParseCertificate(raw)
			if err != nil {
				return fmt.Errorf("parse peer certificate: %w", err)
			}
			for _, uri := range cert.URIs {
				id, err := spiffeid.FromURI(uri)
				if err != nil {
					continue
				}
				if id.TrustDomain() == trustDomain {
					return nil
				}
			}
		}
		return fmt.Errorf("peer certificate missing SPIFFE ID in trust domain %s", trustDomain.String())
	}

	clientID := sanitizeClientID(svid.ID.String())
	return tlsCfg, clientID, nil
}

func sanitizeClientID(spiffeID string) string {
	clientID := strings.ReplaceAll(spiffeID, "spiffe://", "")
	clientID = strings.ReplaceAll(clientID, "/", "-")
	clientID = strings.ReplaceAll(clientID, ":", "-")
	if len(clientID) > 128 {
		clientID = clientID[:128]
	}
	return clientID
}

// ApplySnapshot applies an initial snapshot outside the Run loop.
func (p *Publisher) ApplySnapshot(update *workloadapi.X509Context) error {
	return p.applyUpdate(update)
}
