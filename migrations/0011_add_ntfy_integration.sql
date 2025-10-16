-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'ntfy',
    'ntfy',
    'Real-time notifications delivered via ntfy topics.',
    '🔔',
    0,
    '{"base_url": "", "topic": "", "token": ""}'
WHERE NOT EXISTS (
    SELECT 1 FROM integration_modules WHERE slug = 'ntfy'
);
