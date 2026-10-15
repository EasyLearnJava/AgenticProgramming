import { PromptTemplate } from "@langchain/core/prompts";
import { RunnableLambda } from "@langchain/core/runnables";

// ① The template: the text we want to show.
const prompt = PromptTemplate.fromTemplate("Hello World, welcome to LangChain!");

// ② The converter: the prompt gives back an object, this turns it into text.
const toText = RunnableLambda.from((value) => value.toString());

// ③ Join them: prompt first, then toText.
const chain = prompt.pipe(toText);

// ④ Run it. {} means no input.
const answer = await chain.invoke({});

console.log(answer);
