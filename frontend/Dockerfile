FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* ./
RUN if [ -f package-lock.json ]; then npm ci; \
    elif [ -f pnpm-lock.yaml ]; then corepack enable && pnpm i --frozen-lockfile; \
    elif [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
    else npm i; fi

COPY . .

ARG NEXT_PUBLIC_API_BASE
ARG NEXT_PUBLIC_WS_BASE
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
ENV NEXT_PUBLIC_WS_BASE=${NEXT_PUBLIC_WS_BASE}

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=deps /app ./

EXPOSE 3000

CMD ["npm", "run", "start"]
