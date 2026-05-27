from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="indra-ai",
    version="1.0.0",
    author="Mahika Jadhav",
    author_email="mahikajadhav22@gmail.com",
    description="Web intelligence that only thinks when the web changes. Bright Data + LLM agent cache — zero tokens on unchanged pages.",
    keywords=[
        "web scraping", "bright data", "web monitoring", "change detection",
        "llm cost reduction", "ai agent", "web intelligence", "competitor monitoring",
        "price monitoring", "token savings", "agent cache", "web data",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/smartass-4ever/Indra",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
        "Topic :: Database :: Database Engines/Servers",
    ],
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.24.0",
        "cryptography>=41.0.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "embeddings": ["sentence-transformers>=2.2.0"],
        "anthropic": ["anthropic>=0.20.0"],
        "openai":    ["openai>=1.0.0"],
        "google":    ["google-generativeai>=0.7.0"],
        "groq":      ["groq>=0.9.0"],
        "all-llm": [
            "anthropic>=0.20.0",
            "openai>=1.0.0",
            "google-generativeai>=0.7.0",
            "groq>=0.9.0",
        ],
        "full": [
            "sentence-transformers>=2.2.0",
            "anthropic>=0.20.0",
            "openai>=1.0.0",
            "google-generativeai>=0.7.0",
            "groq>=0.9.0",
        ],
        "redis": ["redis>=5.0.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "indra=indra.cli:main",
        ],
    },
)
   
