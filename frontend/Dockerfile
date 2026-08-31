FROM node:22-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
# Imported by src/seed.ts, one level above the Vite root.
COPY shared /shared

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
