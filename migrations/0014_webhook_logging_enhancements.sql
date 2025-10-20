ALTER TABLE webhook_deliveries
    ADD COLUMN module_id INTEGER REFERENCES integration_modules(id) ON DELETE SET NULL;
ALTER TABLE webhook_deliveries
    ADD COLUMN module_slug VARCHAR(255);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_module_id
    ON webhook_deliveries(module_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_module_slug
    ON webhook_deliveries(module_slug);
ALTER TABLE webhook_deliveries
    ADD COLUMN request_method VARCHAR(16) NOT NULL DEFAULT 'GET';
ALTER TABLE webhook_deliveries
    ADD COLUMN request_url VARCHAR(2048) NOT NULL DEFAULT '';
UPDATE webhook_deliveries SET request_url = endpoint WHERE request_url = '';
ALTER TABLE webhook_deliveries
    ADD COLUMN request_payload JSON;
ALTER TABLE webhook_deliveries
    ADD COLUMN response_status_code INTEGER;
ALTER TABLE webhook_deliveries
    ADD COLUMN response_payload JSON;
ALTER TABLE webhook_deliveries
    ADD COLUMN error_message TEXT;
