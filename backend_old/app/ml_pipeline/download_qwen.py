from sentence_transformers import SentenceTransformer

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

print("Loading model...")

model = SentenceTransformer(
    MODEL_NAME,
    trust_remote_code=True
)

print("Model loaded successfully!")
print("Model:", MODEL_NAME)
print("Embedding dimension:", model.get_sentence_embedding_dimension())