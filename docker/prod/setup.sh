#!/bin/bash

# Determine the script's location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change the current working directory to the script's location
cd "$SCRIPT_DIR"

HOSTNAME=$(grep HOSTNAME .env | cut -d '=' -f2)
EMAIL=admin@slog.ai

# Determine the project root path based on the script's location
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." &> /dev/null && pwd )"

# update and upgrade the server
sudo apt-get update && sudo apt-get upgrade -y

# install python, pip, docker and docker-compose
sudo apt-get install -y python3-pip python3-dev libpq-dev
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh
sudo usermod -aG docker ${USER}
sudo pip3 install docker-compose

# build and up docker containers
sudo -E docker-compose -f docker-compose.yml up --build -d

# install nginx
sudo apt-get install -y nginx

# enable nginx configuration
sudo cp nginx.conf /etc/nginx/sites-available/default

# Replace the domain, static files path, and media path placeholders in nginx.conf
sed -i "s/your-domain.com/${HOSTNAME}/g" /etc/nginx/sites-available/default
sed -i "s|/var/www/project|${PROJECT_ROOT}|g" /etc/nginx/sites-available/default

# restart nginx
sudo systemctl restart nginx

# install certbot and certbot-nginx for SSL certificate
sudo pip3 install certbot certbot-nginx

# obtain and install SSL certificate
sudo certbot --nginx -d ${HOSTNAME} --non-interactive --agree-tos --email ${EMAIL} --redirect

# restart nginx to apply SSL
sudo systemctl restart nginx

# set up automatic certificate renewal and docker system prune
(crontab -l; echo "0 12 * * * /usr/local/bin/certbot renew --quiet"; echo "0 3 */7 * * /usr/bin/docker system prune -af --volumes") | crontab -

