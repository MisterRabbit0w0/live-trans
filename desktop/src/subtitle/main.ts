import { mount } from "svelte";

import "../lib/styles/base.css";
import "../lib/styles/skeuo.css";
import { initStore } from "../lib/store.svelte";
import Overlay from "./Overlay.svelte";

document.documentElement.dataset.window = "subtitle";

void initStore();

mount(Overlay, { target: document.getElementById("app")! });
