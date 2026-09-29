import { mount } from "svelte";

import "../lib/styles/base.css";
import "../lib/styles/skeuo.css";
import { initStore } from "../lib/store.svelte";
import App from "./App.svelte";

void initStore();

mount(App, { target: document.getElementById("app")! });
