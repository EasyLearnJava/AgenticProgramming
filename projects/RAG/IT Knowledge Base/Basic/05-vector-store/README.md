# 05 · Vector store

## What it does

A vector database stores vectors so that they can be searched later. This step stores the 28 chunks in Qdrant, run
as a server by Docker (`docker-compose.yml`). The server has a web dashboard where you can see every stored point.
Qdrant can also run inside the script ("in memory"), with no Docker: then nothing outside the script can see the
points, and they're gone when it ends. See [Run it without Docker](#run-it-without-docker).

`vector_store.py`:

- makes a collection, `it_knowledge_base` (Qdrant's word for a table of points), for vectors of 768 numbers compared
  by cosine similarity: how closely two vectors point the same way;
- loads the articles, cuts them into step 03's 28 chunks and adds them through LangChain's `QdrantVectorStore`.
  `add_documents()` embeds them, with the same call as step 04, and stores each chunk as a point: an id, its vector,
  and a payload with its text (`page_content`) and its labels (`metadata`);
- reads the points back from Qdrant and prints them, to show what was stored.

This is the last step of getting the knowledge base ready to be searched: load, chunk, embed, store. There's still no
question here: the search starts in step 06.

```text
28 chunks  ->  Gemini: 768 numbers each  ->  the Qdrant server: 28 points (vector + text + labels)  ->  the dashboard
```

Each run makes 1 call to Gemini, for all 28 chunks. It embeds them again rather than using step 04's vectors, because
each project runs on its own, from the CSV. Each run also starts fresh: it deletes the collection and stores the
chunks again. The points get random ids, so without that, every run would add 28 more copies. Step 11 does better: it
gives each chunk an id made from its text, and keeps the stored chunks between runs instead of embedding them again.

## How to run it

You need Python 3.11 or newer, a Gemini API key, and Docker (Docker Desktop on Windows and macOS; GitHub Codespaces
has Docker already). To run without Docker, see [Run it without Docker](#run-it-without-docker).

```bash
cd "projects/RAG/IT Knowledge Base/Basic/05-vector-store"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
docker compose up -d                 # start the Qdrant server, in the background (the first time, Docker downloads it)
docker compose ps                    # check: the qdrant service is "Up"
python vector_store.py               # store the 28 chunks in the server
```

Then open the dashboard: http://localhost:6333/dashboard on your own computer, or, in GitHub Codespaces, the address
the **Ports** tab gives for port 6333 (see [Open the dashboard](#open-the-dashboard), below).

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal. The
Qdrant server keeps running in the background until you stop it (see [Stop the server](#stop-the-server)), so next
time you only need `python vector_store.py`.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

`.env` also has `QDRANT_URL=http://localhost:6333`, from `.env.example`: that's what tells the script to use the
server. The script itself runs next to Qdrant, so for it the server is always `localhost`, in Codespaces too.

`python vector_store.py` says where Qdrant is, prints the collection's settings, then every stored point, one line
each: its article, where in the article the chunk starts, its vector's size, its text's length and how many labels it
has. It ends with where to find the dashboard. Gemini's numbers aren't printed, so this is exactly what you'll see:

```text
Qdrant: the server at http://localhost:6333
Collection 'it_knowledge_base': 28 points, vectors of 768 numbers, compared by Cosine
Each point holds an id, a vector and a payload with metadata, page_content

Point 1 of 28: VPN Connection Timeout, from character 0: 768 numbers, 457 characters of text, 7 labels
Point 2 of 28: VPN Connection Timeout, from character 459: 768 numbers, 110 characters of text, 7 labels
Point 3 of 28: MFA Setup Failure, from character 0: 768 numbers, 144 characters of text, 7 labels
...
Point 28 of 28: Microsoft Teams Audio Issues, from character 581: 768 numbers, 118 characters of text, 7 labels

See them in Qdrant's dashboard: http://localhost:6333/dashboard
In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.
```

The 7 labels are the article's 6 from step 02 (`doc_id`, title, system, category, priority, tags), plus
`start_index` from step 03.

### Open the dashboard

| Where you run it | The dashboard's address |
|---|---|
| On your own computer | http://localhost:6333/dashboard |
| In GitHub Codespaces | `https://<codespace-name>-6333.app.github.dev/dashboard` |

In Codespaces, your browser is on your own computer, not in the codespace, so it needs the codespace's forwarded
address. The surest way to get it is the **Ports** tab:

1. Open the **Ports** tab, next to **Terminal**. Codespaces forwards port 6333 once Qdrant is running.
2. If 6333 isn't listed, click **Add Port** and type `6333`.
3. Click the globe icon on the 6333 row: it opens the exact forwarded address for your codespace.
4. Add `/dashboard` to the end of that address.

`<codespace-name>` is the first part of your codespace's own address, for example `silver-lamp-jwjq66xxgphp7rw` in
`silver-lamp-jwjq66xxgphp7rw.github.dev`. The port is private by default: open it in the browser where you're signed
in to GitHub.

In the dashboard, open **Collections**, then `it_knowledge_base`: its 28 points, each with its payload (the chunk's
text and labels) and its vector. If the dashboard says `No collection is present`, the script hasn't stored anything
in this server yet: check that the first line `python vector_store.py` prints is `Qdrant: the server at ...`, then
refresh the page (the ↻ next to **Collections**). If it says `Qdrant: in memory, inside this script`, `.env` has no
`QDRANT_URL` line, or it has a `#` in front: fix it, and run the script again.

### The Visualize tab: every chunk on one map

In `it_knowledge_base`, the **Visualize** tab draws all 28 points as dots on one map. Its right-hand side holds a
request, and nothing is drawn until you click the small **RUN** link just above the request's `{`. To color the dots
by article, replace the request with this one, then click **RUN**:

```json
{
  "limit": 100,
  "color_by": { "payload": "metadata.title" }
}
```

- `limit`: how many points to draw. There are 28, so anything above that draws them all.
- `color_by`: the payload field that picks each dot's color. Our labels are inside `metadata`, so it's
  `metadata.title`.
- If the map stays blank, or **Data Panel** shows an error, add `"algorithm": "PCA"`. The default, UMAP, is made for
  thousands of points; PCA does better with 28.

Each dot is one chunk. The map squeezes each vector's 768 numbers into 2, so it shows roughly which chunks are near
each other, but its distances aren't the real scores.

Click a dot, and **Data Panel** shows that point's payload and, under **Similar points**, the points whose vectors are
closest to it, with their scores. On the map, the clicked dot and those neighbours stay bright, and the rest fade.
Clicking the MFA article's first chunk (its Title and Problem) gives:

![Qdrant's dashboard, Visualize tab, for it_knowledge_base. On the left, 28 dots: the clicked one circled, its nearest neighbours bright, the others faded. On the right, Data Panel shows the clicked point's payload: page_content "Title: MFA Setup Failure Problem: Employee cannot...", and metadata doc_id 1, title MFA Setup Failure, system MFA, category Security, priority High, tags mfa;authentication;mobile;security, start_index 0. Below it, Similar points lists 12 points with their scores, from 0.8691 down to 0.7558 for the last one, bd4a67d9-f0f7-4e02-bf5e-ea47122b9c8e.](images/dashboard-similar-points.png)

#### What the score means: 0.7558

Each score is the cosine similarity between the clicked point's vector and that point's vector: how closely the two
point the same way.

- **1.0** means the same direction, the same meaning; **0** means unrelated.
- **0.7558**, the last one listed, means fairly similar: an angle of about 41° between the two vectors. The top one,
  **0.8691**, is about 30°.

It's the cosine from [How Qdrant measures "close"](#how-qdrant-measures-close-the-distance), below, with 768
numbers instead of 2:

```text
cosine(a, b) = (a₁×b₁ + a₂×b₂ + … + a₇₆₈×b₇₆₈) / (length of a × length of b)
```

The collection uses cosine, so Qdrant stores every vector at length 1 (see
[Why Qdrant's stored numbers differ from Gemini's](#why-qdrants-stored-numbers-differ-from-geminis)). Both lengths
are 1, so the score is just the sum of the 768 products: the two vectors multiplied number by number, then added up.
With 2 numbers, `[0.6, 0.8]` and `[0.8, 0.6]` give `0.6×0.8 + 0.8×0.6 = 0.96`. The Qdrant server does this sum
between the clicked point and every other point, and lists the highest first.

Reading the scores:

- **The order matters more than the values.** All 28 chunks are IT help-desk text, so to Gemini they're all fairly
  similar, and the scores sit close together: 0.76 to 0.87 here. What decides a search, in step 06, is which chunks
  score highest.
- **To see which chunk a score belongs to,** click the eye icon next to it.

#### Check a score yourself

With Qdrant running and the venv active, in this folder, this reads two stored vectors from Qdrant and does the sum
itself, with no call to Gemini. Put in the id of the clicked point and the id of one point from its list:

```bash
python - <<'EOF'
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333", check_compatibility=False)
a, b = client.retrieve("it_knowledge_base", with_vectors=True,
                       ids=["f0f1e50f-598b-42f8-b135-f45456994f00", "bd4a67d9-f0f7-4e02-bf5e-ea47122b9c8e"])
print("length of a:", round(sum(x * x for x in a.vector) ** 0.5, 4))   # 1.0: stored at length 1
print("cosine:", round(sum(x * y for x, y in zip(a.vector, b.vector)), 4))
EOF
```

It prints `length of a: 1.0` and the same score as the dashboard: `0.7558` for the two points in the picture. Each run
of `vector_store.py` stores the points again, with new random ids, so copy the ids from the dashboard after your latest
run.

### If the dashboard says 404 (page can't be found)

In Codespaces, `This ... page can't be found` with `HTTP ERROR 404` comes from Codespaces, not from Qdrant: nothing
is answering on port 6333 inside the codespace. Check, in the codespace's terminal:

1. **You're in this folder, with the latest code.** `docker-compose.yml` must be here:

   ```bash
   cd "projects/RAG/IT Knowledge Base/Basic/05-vector-store"   # from the repo root (/workspaces/AgenticProgramming)
   git pull
   ls docker-compose.yml
   ```

   Without it, `docker compose up -d` stops with `no configuration file provided: not found`.

2. **Qdrant is running.** Start it, then look:

   ```bash
   docker compose up -d
   docker compose ps
   ```

   `docker compose ps` should list the qdrant service with `Up` in its status. If `up -d` printed an error, or `ps`
   lists nothing, Qdrant isn't running: the error says why.

3. **Qdrant answers inside the codespace:**

   ```bash
   curl http://localhost:6333
   ```

   A short JSON reply from Qdrant means it's working. `Connection refused` means it isn't running yet: go back to 2.

4. **The port is forwarded.** Once `curl` works, open the dashboard from the **Ports** tab, as in
   [Open the dashboard](#open-the-dashboard): the globe icon on the 6333 row, then `/dashboard`. Typing the address
   by hand can go wrong; the Ports tab's address can't.

### If Qdrant isn't running

If `QDRANT_URL` is set but no server answers, the script stops before calling Gemini:

```text
Can't reach Qdrant at http://localhost:6333. Start it first, in this folder: docker compose up -d (or remove QDRANT_URL from .env to run Qdrant in memory).
```

### Stop the server

Run `docker compose down` in this folder. Its data stays in a Docker volume for next time (`docker compose down -v`
deletes it). In Codespaces, the server also stops when the codespace stops: run `docker compose up -d` again next
time. Only one server can use port 6333, so stop this one before starting step 11's.

### Run it without Docker

In `.env`, put a `#` at the start of the `QDRANT_URL` line:

```text
# QDRANT_URL=http://localhost:6333
```

Then `python vector_store.py` keeps Qdrant in memory, inside the script. It prints the same collection and points, but
its first line is `Qdrant: in memory, inside this script`, and there's no dashboard line, because there's no server to
look at. To go back to the server, remove the `#`.

### Run the tests

```bash
python -m pytest                     # 22 passed, 2 skipped
```

The 2 skipped tests are live tests: they call the real Gemini, so they run only when your key is set. The tests never
need Docker: an in-memory Qdrant stands in for the server.

## How Qdrant measures "close": the distance

When `make_vector_store()` creates the collection, it also fixes how Qdrant will measure how close two vectors are:

```python
client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
```

Qdrant offers four distances. To see how they differ, take three vectors of 2 numbers instead of 768:

```text
a = [3, 4]     the stored chunk
b = [6, 8]     the same direction as a, twice as long
c = [4, 3]     a slightly different direction, the same length as a
```

Which is closer to `a`, `b` or `c`? The four distances don't agree:

| Distance | What it measures | a vs b | a vs c | Closest to a | Better score |
|---|---|---|---|---|---|
| **Cosine** | the angle between the arrows, ignoring their length | 1.00 | 0.96 | **b** | higher |
| **Dot** | the angle and the lengths, multiplied together | 50 | 24 | **b** | higher |
| **Euclid** | the straight line between the arrows' tips | 5.00 | 1.41 | **c** | lower |
| **Manhattan** | the walk between the tips along the grid lines | 7 | 2 | **c** | lower |

Cosine and Dot say `b`, which points exactly the same way as `a`. Euclid and Manhattan say `c`, whose tip is nearer.
For text, the direction is what carries the meaning, so `b` should win: that's why text embeddings use cosine.

### Cosine: the angle (what this project uses)

![Cosine. Three arrows from the origin on a grid: a to [3, 4], b to [6, 8] along the same line as a, and c to [4, 3]. An arc marks the 16 degree angle between a and c; a and b are 0 degrees apart. Cosine of a and b: 50 / (5 x 10) = 1.00. Cosine of a and c: 24 / (5 x 5) = 0.96. Higher is closer, so b is closest: only the direction counts.](images/cosine.svg)

Cosine divides the dot product by both lengths, so only the angle is left: 1 means the same direction, 0 unrelated,
-1 opposite. `b` scores 1.00 although it's twice as long as `a`.

**Use it for** text embeddings, where the meaning is the direction, and for any vectors that don't already have
length 1, like Gemini's at 768 numbers. If a model's documentation doesn't say otherwise, cosine is the safe choice.

### Dot: the angle and the lengths

![Dot. The same three arrows. A dashed line drops from c's tip onto a's line, and c's shadow along a is 4.8 long. Dot of a and b: 3x6 + 4x8 = 50, that is 5 x 10. Dot of a and c: 3x4 + 4x3 = 24, that is 5 x 4.8. Higher is closer, so b is closest. On vectors of length 1, dot ranks exactly like cosine.](images/dot.svg)

The dot product multiplies the numbers pair by pair and adds them up: `3×6 + 4×8 = 50`. It's the same as `a`'s length
times the other vector's "shadow" on `a`: `b`'s shadow is all of it, 10, so `5 × 10 = 50`; `c`'s is 4.8, so
`5 × 4.8 = 24`. A longer vector scores higher, so length counts as well as direction.

**Use it for** vectors that already have length 1. Then dot and cosine give exactly the same order, and dot is a
little faster. OpenAI's embeddings, and Gemini's at the full 3072 numbers, come back with length 1. Use it also when a
model's documentation says to, or when a longer vector should win on purpose (in some recommendation systems, a longer
vector means a more popular item).

### Euclid: the straight line between the tips

![Euclid. The same three arrows. A dashed line beside a and b runs from a's tip to b's tip: 5.00 long. Another runs from a's tip to c's tip: 1.41 long. Lower is closer, so c is closest, though b points the same way as a.](images/euclid.svg)

The ordinary distance between two points: `√(3² + 4²) = 5.00` from `a`'s tip to `b`'s, `√(1² + 1²) = 1.41` to `c`'s.
Lower is closer, and 0 means the same point. `b` loses because it's long, even though it means the same thing.

**Use it for** data where the actual position matters, not just the direction: image features, sensor readings,
measurements, grouping similar items into clusters. On vectors of length 1 it ranks results in the same order as
cosine.

### Manhattan: the walk along the grid

![Manhattan. The same three arrows. A dashed path walks from a's tip to b's tip along the grid lines: 4 up and 3 across, 3 + 4 = 7. Another walks from a's tip to c's tip: 1 across and 1 down, 1 + 1 = 2. Lower is closer, so c is closest.](images/manhattan.svg)

Like walking city blocks, with no diagonals: add up the differences, `3 + 4 = 7` to `b` and `1 + 1 = 2` to `c`.
Lower is closer.

**Use it for** text rarely. It shows up with other kinds of number data, where one big difference should count for
less than it does with Euclid, which squares every difference.

### Why Qdrant's stored numbers differ from Gemini's

With cosine, Qdrant stores each vector at length 1. It divides every number by the vector's length, which keeps the
direction:

![Normalized. A long grey arrow goes from the origin to [3, 4], length 5: what Gemini returns. A short blue arrow along the same line ends on a dashed circle of radius 1, at [0.6, 0.8]: what Qdrant stores. Every number is divided by 5. The direction, and so every cosine score, stays the same.](images/normalize.svg)

```text
Gemini returns:  [3, 4]        length √(3² + 4²) = 5
Qdrant stores:   [0.6, 0.8]    [3/5, 4/5], length 1
```

The meaning is the direction, and that doesn't change, so every cosine score stays the same. Qdrant does it so that
each search becomes a simple dot product, which is faster. It does this only with cosine; with Dot, Euclid and
Manhattan it stores the vectors exactly as they came. So if you compared the first numbers `embed_chunks.py` prints in
step 04 with the vectors stored here, they'd differ, by the same factor for every number in a vector.

### Choosing a distance

- **Use the distance the embedding model's documentation recommends.** For Gemini's embeddings, that's cosine.
- **It's fixed when the collection is created.** To change it, make a new collection and store the chunks again.
- **It decides what the scores mean.** With cosine and dot, higher is closer; with Euclid and Manhattan, lower is
  closer. The scores step 06 prints read "the closer to 1, the closer the meaning" because this project uses cosine.
