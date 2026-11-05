// Exercise the actual feature modules against the app markup and mocked HTTP.
import test, { beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { parseHTML } from "linkedom";
import { initAsk } from "../web/js/ask.js";
import { initKnowledge, renderKnowledge } from "../web/js/knowledge.js";
import { initEvaluation } from "../web/js/evaluation.js";

const html = await readFile(new URL("../web/index.html", import.meta.url),"utf8");
const originalFetch = globalThis.fetch, originalTimer = globalThis.setTimeout;
let window, document, calls;
const response = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{"Content-Type":"application/json"}});
const ready = {needs_rebuild:false,documents:[],chunk_count:0,chunk_size:500,chunk_overlap:75,top_k:5,freshness_days:7};
const answer = {question:"Receipts?",status:"evidence",text:"Receipt rule [1]",parts:[{text:"The source includes literal [1].",citations:[1]}],
  citations:[{number:1,source_id:"expense",chunk_id:"x",title:"Expense policy",quote:"Keep the receipt.",location:"Receipts",url:"https://example.com/policy"}],
  retrieved:[],trace:[],latency_ms:10,note:"Source evidence"};
const event = (name,extra={}) => Object.assign(new window.Event(name,{bubbles:true,cancelable:true}),extra);
async function until(check) {
  for (let i=0;i<100;i++) {if(check()) return; await new Promise(setImmediate);}
  assert.ok(check(),"Expected UI update did not arrive");
}

beforeEach(() => {
  ({window,document}=parseHTML(html));
  globalThis.document=document;
  calls=[];
  const dialog=document.querySelector("#source-dialog");
  dialog.showModal=()=>dialog.setAttribute("open","");
  dialog.close=()=>dialog.removeAttribute("open");
  // Skip toast lifetimes and shorten polling; network timeouts are still cleared normally.
  globalThis.setTimeout=(fn,ms,...args)=>ms===4500||ms===8500?0:originalTimer(fn,ms===1000?0:ms,...args);
});
afterEach(()=>{globalThis.fetch=originalFetch;globalThis.setTimeout=originalTimer;delete globalThis.document;});

test("ask.js submits the question and opens the matching explicit citation",async()=>{
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return response(answer);};
  initAsk(()=>ready);
  document.querySelector("#question").value="What receipt rule applies?";
  document.querySelector("#ask-form").dispatchEvent(event("submit"));
  await until(()=>Boolean(document.querySelector(".citation-marker")));
  assert.equal(JSON.parse(calls[0].options.body).question,"What receipt rule applies?");
  assert.equal(document.querySelectorAll(".citation-marker").length,1);
  assert.match(document.querySelector(".answer-body").textContent,/literal \[1\]/);
  document.querySelector(".citation-marker").click();
  assert.equal(document.querySelector("#dialog-title").textContent,"Expense policy");
  assert.ok(document.querySelector("#source-dialog").hasAttribute("open"));
});

test("knowledge.js uploads a replacement revision and refreshes collection state",async()=>{
  let refreshed=0;
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return response({replaced:true,message:"Revision replaced"});};
  initKnowledge(async()=>{refreshed++;});
  const input=document.querySelector("#file-input");
  Object.defineProperty(input,"files",{value:[new File(["A revised policy"],"policy.md")]});
  input.dispatchEvent(event("change"));
  await until(()=>refreshed===1);
  assert.equal(calls[0].url,"/api/documents");
  assert.equal(calls[0].options.body.get("file").name,"policy.md");
});

test("knowledge.js removes and restores uploads through the real event handlers",async()=>{
  let refreshed=0;
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,options});
    if(url.endsWith("/removed")) return response([{source_id:"upload-x",title:"Policy.md"}]);
    return response({message:"Collection changed"});
  };
  initKnowledge(async()=>{refreshed++;});
  renderKnowledge({...ready,documents:[{source_id:"upload-x",title:"Policy.md",category:"Uploaded",kind:"Your document",chunks:1,indexed:true}]});
  document.querySelector("[data-remove]").click();
  await until(()=>refreshed===1);
  assert.equal(calls[0].options.method,"DELETE");
  document.querySelector("#removed-documents").click();
  await until(()=>Boolean(document.querySelector("[data-restore]")));
  document.querySelector("[data-restore]").click();
  await until(()=>refreshed===2);
  assert.equal(calls.at(-1).url,"/api/documents/upload-x/restore");
  assert.ok(!document.querySelector("#source-dialog").hasAttribute("open"));
});

test("evaluation.js polls results, exposes failed checks, and preserves download keys",async()=>{
  const report={id:"a".repeat(32),created_at:"2026-11-05T00:00:00Z",mode:"extractive",top_k:5,
    summary:{questions:1,errors:1,source_recall_at_k:0,chunk_precision_at_k:0,case_pass_rate:0,p95_latency_ms:null,behavior_pass_rate:0},
    cases:[{id:"T1",question:"A failed test",category:"Regression",status:"error",case_pass:false,behavior_pass:false,
      latency_ms:null,analysis:"Provider failed",answer:{text:"No result"}}]};
  globalThis.fetch=async(url,options={})=>{calls.push({url,options});return response(options.method==="POST"
    ?{id:"job",status:"running",total:1}:{status:"completed",completed:1,total:1,report});};
  initEvaluation(()=>ready);
  document.querySelector("#evaluate-button").click();
  await until(()=>Boolean(document.querySelector(".evaluation-table")));
  assert.match(document.querySelector(".evaluation-table").textContent,/REVIEW/);
  assert.match(document.querySelector(".evaluation-table").textContent,/—/);
  const row=document.querySelector("[data-case]");
  row.dispatchEvent(event("keydown",{key:"Enter"}));
  assert.ok(!document.querySelector(".case-detail").classList.contains("hidden"));
  const link=document.querySelector(".download-actions a");
  const key=event("keydown",{key:"Enter"});link.dispatchEvent(key);
  assert.equal(key.defaultPrevented,false);
  assert.ok(calls.some(call=>call.url==="/api/evaluations/job"));
});
