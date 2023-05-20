# Twooter

Retrieve tweets from a twitter account (without login) and repost with media to a mastodon account.

See env_sample for environment variables that need to be included in a .env file.

To run as a service:
1) update paths in sample.service and copy it to /etc/systemd/system/twooter.service.
2) `sudo systemctl daemon-reload`
3) Enable it: `sudo systemctl enable twooter.service`
4) Start it: `sudo systemctl start twooter.service`
5) View logs: `journalctl -u twooter.service`
