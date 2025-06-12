#!/bin/bash
#
# Rough notes on setting up apache2 on a VM with basistech certs

if [ ! -r $HOME/basistech.crt ]; then
    echo install basistech.crt and basistech.key in $HOME
    exit 1
fi
   
# Set up certificates
sudo mkdir -p /etc/ssl/basistech.net/
sudo cp $HOME/basistech.{pem,key} /etc/ssl/basistech.net/
wget https://certs.godaddy.com/repository/gdig2.crt
openssl x509 -in gdig2.crt -text -noout | grep 'Subject\|Issuer'
openssl x509 -inform DER -in gdig2.crt -out gdig2.pem
sudo mv gdig2.pem /etc/ssl/basistech.net/gdig2.pem
cat /etc/ssl/basistech.net/basistech.pem  /etc/ssl/basistech.net/gdig2.pem.pem  | sudo tee /etc/ssl/basistech.net/intermediate.pem
sudo chmod 600 /etc/ssl/basistech.net/*.key
sudo chown root /etc/ssl/basistech.net/*.key
echo edit /etc/apache2/sites-available/default-ssl.conf

if [ ! -r /usr/sbin/ngix ]; then
    sudo apt update
    sudo apt install nginx
    sudo systemctl enable ngix
    sudo systemctl start ngix
fi

sudo apt install python3.12-venv

sudo cp basistech_air.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable basistech_air
sudo systemctl start basistech_air

