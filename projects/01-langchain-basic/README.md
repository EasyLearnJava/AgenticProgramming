# 01 · LangChain basic

The smallest LangChain example: a `PromptTemplate` piped into a `RunnableLambda`, invoked once.
No model, no API key. It prints:

```text
Hello World, welcome to LangChain!
```

## What you learn

- `PromptTemplate`: holds the text, here with no variables to fill in
- `.pipe()`: sends one Runnable's output into the next
- `.invoke()`: runs the chain and returns the result

## Files

| File | What it is |
|---|---|
| `hello.js` | The chain: `prompt.pipe(toText)`, invoked with `{}` |
| `package.json` | One dependency: `@langchain/core` 1.2.17 |

## Run it

```bash
npm install   # once
npm start     # node hello.js -> Hello World, welcome to LangChain!
```

Change the text in `hello.js` and run `npm start` again to see it change.

## Next

The chain runs once, by itself. The next project builds on it.
