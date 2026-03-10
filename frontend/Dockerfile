FROM node:20-alpine

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

COPY package.json /app/package.json
RUN pnpm install

COPY . /app

CMD ["pnpm", "dev"]
