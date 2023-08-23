#!/bin/bash

# Determine the script's location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change the current working directory to the script's location
cd "$SCRIPT_DIR"

HOSTNAME=$(grep HOSTNAME .env | cut -d '=' -f2)
PORT=$(grep DJANGO_PORT .env | cut -d '=' -f2)
EMAIL=admin@slog.ai

# Determine the project root path based on the script's location
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." &> /dev/null && pwd )"

# update and upgrade the server
sudo apt-get update && sudo apt-get upgrade -y

# install python, pip, docker and docker-compose if not already present
if ! command -v docker &> /dev/null; then
    sudo apt-get install -y python3-pip python3-dev libpq-dev
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker ${USER}
else
    echo "Docker is already installed. Skipping..."
fi
if ! command -v docker-compose &> /dev/null; then
    sudo pip3 install docker-compose
else
    echo "Docker-compose is already installed. Skipping..."
fi

# build and up docker containers
sudo -E docker-compose -f docker-compose.yml up --build -d

# install nginx if not already present
if ! command -v nginx &> /dev/null; then
    sudo apt-get install -y nginx
else
    echo "Nginx is already installed. Skipping..."
fi

# enable nginx configuration
sudo cp nginx.conf /etc/nginx/sites-available/$HOSTNAME
sudo ln -s /etc/nginx/sites-available/$HOSTNAME /etc/nginx/sites-enabled/

# Replace the domain, static files path, and media path placeholders in nginx.conf
sed -i "s/your-domain.com/${HOSTNAME}/g" /etc/nginx/sites-available/$HOSTNAME
sed -i "s/:8000/:${PORT}/g" /etc/nginx/sites-available/$HOSTNAME
sed -i "s|/var/www/project|${PROJECT_ROOT}|g" /etc/nginx/sites-available/$HOSTNAME

# restart nginx
sudo systemctl restart nginx

# install certbot and certbot-nginx for SSL certificate
sudo pip3 install --upgrade certbot certbot-nginx

# obtain and install SSL certificate
sudo certbot --nginx -d ${HOSTNAME} --non-interactive --agree-tos --email ${EMAIL} --redirect

# restart nginx to apply SSL
sudo systemctl restart nginx

# set up automatic certificate renewal if not already present
if ! (crontab -l | grep -q "/usr/local/bin/certbot renew --quiet"); then
    (crontab -l; echo "0 12 * * * /usr/local/bin/certbot renew --quiet") | crontab -
else
    echo "Certbot renewal cron job already exists. Skipping..."
fi

# set up docker system prune if not already present
if ! (crontab -l | grep -q "/usr/bin/docker system prune -af --volumes"); then
    (crontab -l; echo "0 3 */7 * * /usr/bin/docker system prune -af --volumes") | crontab -
else
    echo "Docker prune cron job already exists. Skipping..."
fi
