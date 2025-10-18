-- dialect: all
UPDATE integration_modules
SET
    name = 'HTTPS POST Webhook Receiver',
    slug = 'https-post-receiver',
    description = 'Accepts generic HTTPS POST payloads, logs inbound requests, and exposes mapped automation variables.',
    icon = COALESCE(icon, '💬')
WHERE slug = 'discord-webhook-receiver';

INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'HTTPS POST Webhook Receiver',
    'https-post-receiver',
    'Accepts generic HTTPS POST payloads, logs inbound requests, and exposes mapped automation variables.',
    '💬',
    0,
    '{}'
WHERE NOT EXISTS (
    SELECT 1 FROM integration_modules WHERE slug = 'https-post-receiver'
);
