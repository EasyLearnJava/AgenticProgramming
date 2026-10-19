# 01 · LangChain basic

LangChain is a library for building apps around language models: you join small steps into a chain, and each step's
output goes into the next. This project joins two steps, a prompt and a converter, into a chain in JavaScript, with
no model yet, so you can see how steps are joined and run.

```text
{}  ->  prompt  ->  a StringPromptValue  ->  toText  ->  "Hello World, welcome to LangChain!"
```

## What you'll build

- `hello.js`: a chain of two steps, a `PromptTemplate` piped into a `RunnableLambda`, run once.
- `package.json`: the one package the project needs, `@langchain/core` 1.2.14, and the `start` script that runs
  `hello.js`.
- What you see: `npm start` prints `Hello World, welcome to LangChain!` in your terminal. No server, no page, no
  model, no API key.

## What you'll learn

- **`PromptTemplate.fromTemplate()`**: holds the text; its `invoke()` gives back a `StringPromptValue`, not a string
- **`RunnableLambda.from()`**: wraps a plain function as a Runnable, with `invoke()` and `pipe()` like the prompt
- **Runnables and `.pipe()`**: `a.pipe(b)` joins two Runnables into a `RunnableSequence`; building it runs nothing
- **`await chain.invoke({})`**: runs the chain; in LangChain.js `invoke()` returns a Promise, so you `await` it
- **npm basics**: `package.json`, `package-lock.json`, `npm install`, `npm start` and `"type": "module"`

## Before you start

- **Node.js 20 or newer** (22 is used here). Check with `node --version`; if that fails, install Node from
  nodejs.org, which includes npm (`npm --version`). `@langchain/core` 1.2.14 asks for Node 20 or newer.
- Nothing else: no Python and no API key.

## Files

| File | What it is |
|---|---|
| `hello.js` | The chain: `prompt.pipe(toText)`, run once with `invoke({})`, and the answer printed |
| `package.json` | The project's settings for npm: one package, `@langchain/core` pinned at 1.2.14; the `start` script (`node hello.js`); `"type": "module"` |
| `package-lock.json` | The exact version of every package `npm install` puts in `node_modules/` (`@langchain/core` and the packages it needs). Written by npm: don't edit it by hand |
| `images/` | The two pictures on this page: `hello.js` running from top to bottom, and the commands that run it. They're SVG files: pictures written as text, which GitHub shows as images |
| `README.md` | This page |

## How it works

### `npm install`, then `npm start`

All of the project's setup is in `package.json`:

```json
{
  "name": "01-langchain-basic",
  "private": true,
  "type": "module",
  "description": "Project 1: the smallest LangChain chain, a PromptTemplate piped into a RunnableLambda, invoked once.",
  "scripts": {
    "start": "node hello.js"
  },
  "dependencies": {
    "@langchain/core": "1.2.14"
  }
}
```

- **`"dependencies"`**: the one package this project uses, pinned to an exact version. `npm install` downloads it,
  and the packages it needs in turn, into a `node_modules/` folder, at the versions listed in `package-lock.json`.
  Both files are in git, so everyone gets the same versions; `node_modules/` is not: `npm install` makes it on your
  machine.
- **`"scripts"`**: `npm start` runs the `start` script, `node hello.js`. npm prints the script (`> node hello.js`)
  before running it.
- **`"type": "module"`**: tells Node that the `.js` files here are ES modules, the modern JavaScript module format.
  `hello.js` is one: it has `import` lines and an `await` outside any function, in ④.

### `hello.js`, from top to bottom

`npm start` runs `node hello.js`, and Node runs the file's statements one after the other, from the top:

![hello.js from top to bottom. The imports take PromptTemplate and RunnableLambda from @langchain/core. ① makes prompt, ② makes toText and ③ makes chain, which joins them: none of them runs yet. ④ chain.invoke({}) runs the chain: {} goes into prompt, which gives a StringPromptValue to toText, which gives back the string; await waits for the chain to finish, and answer holds "Hello World, welcome to LangChain!". console.log(answer) prints it in the terminal.](images/hello-js.svg)

① to ③ only make things: `prompt`, `toText`, and `chain`, which joins them. None of them runs yet. ④ is where the
work happens: `chain.invoke({})` runs `prompt`, then `toText`, and `answer` gets the string. Then `console.log`
prints it. The sections below go through the statements one at a time.

### The imports

```js
import { PromptTemplate } from "@langchain/core/prompts";
import { RunnableLambda } from "@langchain/core/runnables";
```

Each line takes one name from a part of the `@langchain/core` package. `@langchain/core` is LangChain's base
package: the building blocks, such as prompts and Runnables, and no connection to any model.

### ① The template

```js
const prompt = PromptTemplate.fromTemplate("Hello World, welcome to LangChain!");
```

`fromTemplate()` turns a text into a prompt template. This text is fixed, so each time the prompt runs it gives back
the same words, inside a `StringPromptValue`.

### ② The converter

```js
const toText = RunnableLambda.from((value) => value.toString());
```

The prompt doesn't give back a string: `prompt.invoke({})` gives back a `StringPromptValue`, a LangChain object with
the text inside ([Things to try](#things-to-try) prints one). `toText` turns it into text:

- `(value) => value.toString()` is a small function (an arrow function): it takes the `StringPromptValue` and
  returns the text inside it.
- `RunnableLambda.from()` wraps that function as a **Runnable**, LangChain's word for a step: something with
  `invoke()` to run it and `pipe()` to join it to the next step. The prompt is a Runnable too.

### ③ The chain

```js
const chain = prompt.pipe(toText);
```

`pipe()` joins the two steps into a new Runnable, a `RunnableSequence`: what `prompt` gives back goes into `toText`.
Building it runs nothing: no step is called until `invoke()`, in ④.

### ④ Running it

```js
const answer = await chain.invoke({});

console.log(answer);
```

| Step | Gets | Gives back |
|---|---|---|
| `prompt` | `{}` | a `StringPromptValue` |
| `toText` | that `StringPromptValue` | the string `Hello World, welcome to LangChain!` |
| `chain` (both steps, in order) | `{}` | the same string |

- `{}` is the input: an empty object, because this template has nothing to fill in.
- `invoke()` returns a Promise (an answer that arrives later), so `await` waits for it and gives back the string.
- An `await` outside any function is allowed because this file is an ES module (`"type": "module"`).
- `console.log(answer)` prints the string.

## Run it

```bash
cd tutorials/01-langchain-basic   # from the repo root
npm install                      # once: downloads @langchain/core into node_modules/
npm start                        # runs node hello.js
```

![A terminal. cd tutorials/01-langchain-basic goes into the project's folder. npm install, once, downloads @langchain/core and the packages it needs into node_modules/, then prints its report: added 12 packages, and found 0 vulnerabilities, information only. npm start, each time, runs the start script in package.json, node hello.js: npm shows > start and > node hello.js, then console.log(answer) prints Hello World, welcome to LangChain! and the program ends.](images/run-it.svg)

`npm start` prints:

```text
> start
> node hello.js

Hello World, welcome to LangChain!
```

The two `>` lines are npm showing the script it runs; the last line is `hello.js`'s `console.log`. `node hello.js`
runs the same file and prints only that last line. There's no server, page or port in this project: the line
appears in the same terminal, and the program ends. In Windows PowerShell, if `npm` is refused, see
[When things go wrong](#when-things-go-wrong).

## Test it

No automated tests: the whole program is one chain that prints one line, so running it is the test. `npm start`
should print `Hello World, welcome to LangChain!`.

## When things go wrong

An error can print many lines. The "What you see" column quotes the part that says what went wrong.

| What happens | What you see | What to do |
|---|---|---|
| `npm start` before `npm install` | `Error [ERR_MODULE_NOT_FOUND]: Cannot find package '@langchain/core' imported from ...hello.js` | Run `npm install` in this folder, then `npm start` |
| `npm start` in another folder, such as the repo root | `npm error enoent Could not read package.json: Error: ENOENT: no such file or directory, ...` | `cd tutorials/01-langchain-basic` first |
| `npm` in Windows PowerShell | `npm.ps1 cannot be loaded because running scripts is disabled on this system` | Type `npm.cmd` instead of `npm` (`npm.cmd install`, `npm.cmd start`), or use Git Bash or Command Prompt. Or allow scripts for your Windows user once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

## Things to try

1. **Change the text.** Replace the words in `fromTemplate("...")`, for example with `"Hi there, LangChain!"`, and
   run `npm start` again: it prints `Hi there, LangChain!`. Leave out `{` and `}`: they have a special meaning in a
   template, and `npm start` would stop with an error.
2. **See what the prompt gives back.** Change the line under ③ to `const chain = prompt;`, the prompt alone,
   without `toText`. Instead of the line, it prints the object:

   ```text
   StringPromptValue {
     lc_serializable: true,
     lc_kwargs: { value: 'Hello World, welcome to LangChain!' },
     lc_namespace: [ 'langchain_core', 'prompt_values' ],
     value: 'Hello World, welcome to LangChain!'
   }
   ```

   That object is why `toText` is there.
3. **Forget the `await`.** Change the line under ④ to `const answer = chain.invoke({});`. It prints
   `Promise { <pending> }`:
   `console.log` ran before the chain had finished, so it printed the Promise instead of the answer.

## Next

**[Project 02 · LangChain basic (Python)](../02-langchain-python/README.md)**: the same chain in Python, served by a
FastAPI server to a web page that calls it as soon as it opens, with the first tests.
