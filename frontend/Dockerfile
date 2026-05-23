# 前端镜像：构建阶段安装依赖，运行阶段直接启动。
FROM node:20-alpine

WORKDIR /app

COPY package*.json /app/
RUN npm install

COPY . /app

EXPOSE 3000
