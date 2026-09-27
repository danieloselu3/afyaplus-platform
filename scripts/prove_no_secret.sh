#!/usr/bin/env bash
# prove_no_secret.sh - show a reviewer the JWT secret is not baked into the image.
# Usage: bash scripts/prove_no_secret.sh afyaplus-triage:1.0.0
IMAGE="${1:?image tag required}"

echo "=== 1. Fresh container WITHOUT --env-file: environment and files"
echo "\$ docker run --rm --entrypoint sh $IMAGE -c 'env | sort; ls -la /app'"
docker run --rm --entrypoint sh "$IMAGE" -c 'env | sort; echo; ls -la /app'
echo
echo "\$ ... | grep -c -E 'JWT_SECRET|OPENAI_API_KEY'   (0 = absent)"
docker run --rm --entrypoint sh "$IMAGE" -c 'env' | grep -c -E 'JWT_SECRET|OPENAI_API_KEY'
echo
echo "=== 2. Same image started normally WITHOUT secrets: it refuses to boot (APP_ENV=production)"
echo "\$ docker run --rm $IMAGE"
docker run --rm "$IMAGE" 2>&1 | tail -3
echo
echo "=== 3. WITH --env-file .env: secrets present only at runtime (values masked)"
echo "\$ docker run --rm --env-file .env --entrypoint sh $IMAGE -c 'env | grep ...'"
docker run --rm --env-file .env --entrypoint sh "$IMAGE" -c 'env | grep -E "JWT_SECRET|OPENAI_API_KEY"' | sed -E 's/=.*/=<present, value masked>/'
echo
echo "=== 4. Image history: no layer mentions the secret"
echo "\$ docker history --no-trunc $IMAGE | grep -c -E 'JWT_SECRET=|OPENAI_API_KEY='   (0 = absent)"
docker history --no-trunc "$IMAGE" | grep -c -E 'JWT_SECRET=|OPENAI_API_KEY='
