FROM nginx:1.29.3-alpine

COPY deploy/nginx/nginx.prod.conf /etc/nginx/nginx.conf
