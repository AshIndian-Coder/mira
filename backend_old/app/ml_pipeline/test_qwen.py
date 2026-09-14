from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

print("Loading Qwen model...")

model = SentenceTransformer(
    MODEL_NAME,
    trust_remote_code=True
)

texts = [
    "BRG BALL 6205 2RS",
    "BALL BEARING 6205 2RS",
    "BRG BALL 6305 2RS"
]

print("Generating embeddings...")

embeddings = model.encode(
    texts,
    normalize_embeddings=True
)

print("\nEmbedding shape:", embeddings.shape)

similarity_matrix = cosine_similarity(embeddings)

print("\nCosine Similarity Matrix:")
print(similarity_matrix)

print("\nResults:")
print(f"6205 vs 6205: {similarity_matrix[0][1]:.4f}")
print(f"6205 vs 6305: {similarity_matrix[0][2]:.4f}")
