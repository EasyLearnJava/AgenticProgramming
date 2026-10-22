# 1 · Vector Space Models and Embeddings in RAGs

Code for course 1 of the Pluralsight path *Retrieval Augmented Generation (RAG) for Developers*. The course explains
embeddings with slides and no code; this notebook shows its ideas in ten short code cells, most of them on real text.
Built with **sentence-transformers** (the library that runs a small embedding model, `all-MiniLM-L6-v2`, on the CPU)
and **scikit-learn**.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/EasyLearnJava/AgenticProgramming/blob/main/projects/RAG/IT%20Knowledge%20Base/RAG%20series/1.Vector%20Space%20Models%20and%20Embeddings%20in%20RAGs/vector_space_models_and_embeddings.ipynb)

> **Needs:** a browser and a Google account, for Google Colab. Or, to run it yourself: a GitHub Codespace, or Linux
> or a Mac with Apple silicon, with Python 3.12 or newer.

---

## 🎯 What This Notebook Does

| Section | The course's idea | What the cell shows |
|---|---|---|
| 1. An embedding is a list of numbers | Text becomes a vector; context changes the meaning | 3 sentences with "bank" → 384 numbers each, and how close they are |
| 2. TF-IDF counts words | Sparse vectors miss meaning | Two documents about a car score 0.0: they share no word |
| 3. Word2Vec's idea | king − man + woman ≈ queen | The vector arithmetic, with "queen" nearest of 7 candidates |
| 4. Search, match, rank | The three steps of retrieval | "AI writing tools" finds "Chatbots for content creation"; "climate change effects" ranks the global warming document first |
| 5. Three similarity metrics | Cosine, Euclidean, dot product | Where cosine and Euclidean disagree, on two short vectors |
| 6. Dimensionality reduction | Compress vectors with PCA | 8 words from 384 numbers to 2, grouped by meaning |
| 7. How fast storage grows | Billions of vectors need terabytes | 1 billion × 768 numbers × 4 bytes ≈ 3.07 TB |

**Try it:** open it in Colab with the button above, and click **Runtime → Run all**.

---

## 🚀 Quick Start

### Option 1: Google Colab (nothing to install)

1. Click **Open in Colab** above. Colab opens the notebook straight from GitHub. Your changes aren't saved anywhere
   unless you choose **File → Save a copy in Drive**.
2. Click **Runtime → Run all**. If Colab warns that the notebook wasn't authored by Google, choose **Run anyway**.
3. The first cell installs what Colab doesn't have yet, and the second downloads the model (about 90 MB). Then every
   cell prints its result under it.

### Option 2: Run It Yourself

In a GitHub Codespace, or on Linux or a Mac:

```bash
cd "projects/RAG/IT Knowledge Base/RAG series/1.Vector Space Models and Embeddings in RAGs"   # from the repo root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # sentence-transformers, PyTorch (CPU only), scikit-learn, the kernel, pytest
```

Then open `vector_space_models_and_embeddings.ipynb` in VS Code, pick the `.venv` kernel (**Select Kernel** →
**Python Environments...**), and click **Run All**. Outside Colab, the first cell installs nothing.

---

## 📁 Project Structure

```text
1.Vector Space Models and Embeddings in RAGs/
├── vector_space_models_and_embeddings.ipynb   # the notebook: 10 code cells, saved with their results
├── tests/
│   └── test_notebook.py                       # 8 tests: runs every cell, then checks what each one printed
├── requirements.txt                           # sentence-transformers, PyTorch (CPU), scikit-learn, NumPy, the kernel
├── requirements-dev.txt                       # requirements.txt plus pytest, nbclient and nbformat, for the tests
├── pytest.ini                                 # finds the tests in tests/
└── README.md                                  # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 8 passed     (add -v for one line per test)
```

The tests run the whole notebook in a new kernel, as **Run All** does, with `nbclient`, then check what the cells
printed: no cell fails, and the first installs nothing outside Colab; each sentence becomes 384 numbers and the money
sentences are closest; TF-IDF gives the two car documents 0.0; "queen" comes out nearest; the meaning match comes
first in search and ranking; the metrics and the storage sum print their exact values; the results saved in the
notebook are the ones a run prints, numbers to within 0.01; and the notebook opens with its Colab link.

---

## 📊 Understanding the Output

Section 4's three steps, as the notebook prints them:

```text
0.486  Chatbots for content creation
0.100  Global warming impacts on agriculture
0.035  Political debates on energy policy

doctor · physician: 0.860
doctor · banana: 0.338
car · automobile: 0.865
car · banana: 0.390

0.641  Global warming impacts on agriculture
0.253  Political debates on energy policy
```

Each number is a cosine similarity: higher means closer in meaning, and 1 means the same. With this model, even
unrelated words score around 0.3 to 0.4. "car" and "automobile" score 0.865, though the TF-IDF documents in section
2, which share no word, scored 0.0. The scores come from sentence-transformers 6.2.0 with PyTorch 2.14.1; on another
computer, or with Colab's own versions, the last digit can differ.

---

## 🛠️ Troubleshooting

**Issue**: In Colab, a warning about `HF_TOKEN` or Colab secrets appears under the model cell.
**Fix**: Nothing to fix. The model is public, so it downloads without a Hugging Face token.

**Issue**: On Windows, `pip install` stops with `ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: '...\.venv\Lib\site-packages\jedi\...'` and a hint about Windows Long Path support.
**Fix**: One file the notebook's kernel needs ends up more than 260 characters from the drive letter when the repo
sits deep in your folders, and Windows refuses longer paths unless long paths are on. Use Colab (Option 1) instead.

**Issue**: `ModuleNotFoundError: No module named 'sentence_transformers'`
**Fix**: The notebook is running on a Python without the packages. In Colab, run the first cell; elsewhere, pick the
`.venv` kernel or install the packages into it (Option 2).

---

## 📚 Next Steps

**[Entry · V1 · RAG in a Notebook](../../Entry/V1/README.md)**: this notebook compared embeddings directly. V1 stores
them in a vector database, Chroma, and searches it with a question.
