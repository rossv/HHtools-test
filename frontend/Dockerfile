# Build stage
FROM node:20-alpine as build
WORKDIR /ui
COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* .npmrc* ./ 2>/dev/null || true
RUN npm install
COPY . .
RUN npm run build

# Serve
FROM nginx:1.27-alpine
COPY --from=build /ui/dist /usr/share/nginx/html
EXPOSE 80
