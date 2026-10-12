FROM node:20-alpine

WORKDIR /app

# Install npm dependencies
COPY package*.json ./
RUN npm install

# Copy application source code
COPY . .

# Expose Vite development server port
EXPOSE 5173

# Run Vite development server bound to all interfaces
CMD ["npm", "run", "dev"]
