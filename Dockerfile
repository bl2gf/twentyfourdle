FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 game && mkdir -p /app/data && chown game:game /app/data
COPY --chown=game:game game.py server.py puzzles.json ./
COPY --chown=game:game public/ ./public/
USER game
ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["python", "server.py"]
