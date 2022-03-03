#!/bin/bash

# run this prior to first run to register SSL certs

# import .env variables
# export $(egrep -v '^#' .env | xargs)
export $(xargs <.env)

# set system timezone
timedatectl set-timezone $TZ

# replace 'VAR_DOMAIN_NAME' in nginx config
sed -i "s/VAR_DOMAIN_NAME/$DOMAIN/g" data/nginx/app.conf

# begin SSL cert fetch
domains=($DOMAIN www.$DOMAIN)
rsa_key_size=4096
data_path="./data/certbot"
email=$SSL_EMAIL # adding a valid address is strongly recommended
staging=0 # set to 1 if testing to avoid hitting request limits

if [ -d "$data_path" ]; then
  read -p "existing data found for $domains. continue and replace existing certificate? (y/N) " decision
  if [ "$decision" != "Y" ] && [ "$decision" != "y" ]; then
    exit
  fi
fi

if [ ! -e "$data_path/conf/options-ssl-nginx.conf" ] || [ ! -e "$data_path/conf/ssl-dhparams.pem" ]; then
  echo "### downloading recommended TLS parameters ..."
  mkdir -p "$data_path/conf"
  curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "$data_path/conf/options-ssl-nginx.conf"
  curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "$data_path/conf/ssl-dhparams.pem"
  echo
fi

echo "### creating dummy certificate for $domains ..."
path="/etc/letsencrypt/live/$domains"
mkdir -p "$data_path/conf/live/$domains"
docker-compose run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:1024 -days 1\
    -keyout '$path/privkey.pem' \
    -out '$path/fullchain.pem' \
    -subj '/CN=localhost'" certbot
echo


echo "### starting nginx ..."
docker-compose up --force-recreate -d
echo

echo "### deleting dummy certificate for $domains ..."
docker-compose run --rm --entrypoint "\
  rm -Rf /etc/letsencrypt/live/$domains && \
  rm -Rf /etc/letsencrypt/archive/$domains && \
  rm -Rf /etc/letsencrypt/renewal/$domains.conf" certbot
echo


echo "### requesting Let's Encrypt certificate for $domains ..."

# join $domains to -d args
domain_args=""
for domain in "${domains[@]}"; do
  domain_args="$domain_args -d $domain"
done

# select appropriate email argument
case "$email" in
  "") email_arg="--register-unsafely-without-email" ;;
  *) email_arg="--email $email" ;;
esac

# enable staging mode if needed
if [ $staging != "0" ]; then staging_arg="--staging"; fi

docker-compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $email_arg \
    $domain_args \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --eff-email \
    --force-renewal" certbot
echo

echo "### reloading nginx ..."
docker-compose exec nginx nginx -s reload
