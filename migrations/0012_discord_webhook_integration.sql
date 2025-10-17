-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'Discord Webhook Receiver',
    'discord-webhook-receiver',
    'Accepts Discord webhook payloads and exposes automation variables.',
    '💬',
    0,
    '{}'
WHERE NOT EXISTS (
    SELECT 1 FROM integration_modules WHERE slug = 'discord-webhook-receiver'
);
