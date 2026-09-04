# 汇诊前端镜像（构建产物 + nginx 反代后端）
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm install --no-audit --no-fund
COPY frontend/ /app/
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
