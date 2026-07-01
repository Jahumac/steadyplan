# Lightweight static Nginx image to serve the client-side SPA
FROM nginx:alpine

# Copy static website files and single-page React app
COPY ./site /usr/share/nginx/html

# Expose port 80 for the Nginx server
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
