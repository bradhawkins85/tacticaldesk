-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'SMTP Email',
    'smtp-email',
    'Send transactional automation updates via authenticated SMTP servers.',
    '✉️',
    0,
    '{"smtp_host": "", "smtp_port": 587, "smtp_username": "", "smtp_password": "", "smtp_sender": "", "smtp_bcc": "", "smtp_use_tls": true, "smtp_use_ssl": false}'
WHERE NOT EXISTS (
    SELECT 1 FROM integration_modules WHERE slug = 'smtp-email'
);
