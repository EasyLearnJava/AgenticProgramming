/*
 * Project 1: the smallest LangChain chain, in JavaScript (LangChain.js). No model, no API key.
 *
 *     prompt (PromptTemplate: the text)  .pipe()  toText (RunnableLambda: StringPromptValue -> string)
 *
 * Run it in this folder:   npm start   (runs node hello.js)   ->   Hello World, welcome to LangChain!
 */
import { PromptTemplate } from "@langchain/core/prompts";
import { RunnableLambda } from "@langchain/core/runnables";

// ① The template: the text we want to show.
const prompt = PromptTemplate.fromTemplate("Hello World, welcome to LangChain!");

// ② The converter: the prompt gives back an object (a StringPromptValue), this turns it into text.
//    RunnableLambda.from() wraps a plain function as a Runnable: a step with invoke() and pipe(), like the prompt.
const toText = RunnableLambda.from((value) => value.toString());

// ③ Join them: prompt first, then toText. pipe() only builds the chain (a RunnableSequence); nothing runs yet.
const chain = prompt.pipe(toText);

// ④ Run it with {}: an empty input, since the template has nothing to fill in. invoke() returns a Promise, so we
//    await it. await can sit outside a function because package.json makes this an ES module ("type": "module").
const answer = await chain.invoke({});

console.log(answer);
