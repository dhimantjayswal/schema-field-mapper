# Packages the pipeline itself — not the databases (those are plain
# upstream mysql/mongo images in docker-compose.yml, seeded by the scripts
# under docker/mysql-init and docker/mongo-init).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image at build time rather than
# downloading it on first run — makes `docker run` reliable offline/on an
# unfamiliar demo machine instead of depending on network at the worst
# possible moment.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY data ./data
COPY pipeline ./pipeline
COPY run_pipeline.py evaluate_mapping.py ./

ENTRYPOINT ["python", "run_pipeline.py"]
CMD ["--verbose"]
