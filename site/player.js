// Plays a Videotape tape in the page, the way TapePlayer does on macOS: it rests on a state's key, maps a click to the
// hotspot drawn there, and plays that move's clip. Back plays the last move reversed. Switching the story keeps the
// state, since both stories film the same screenplay.

const root = document.querySelector("#player");
const screen = root.querySelector(".screen");
const key = root.querySelector(".key");
const clip = root.querySelector(".clip");
const hotspots = root.querySelector(".hotspots");
const start = root.querySelector(".start");
const back = root.querySelector("[data-act=back]");
const restart = root.querySelector("[data-act=restart]");
const showHotspots = root.querySelector("[data-act=hotspots]");
const typing = root.querySelector(".typing");
const typed = typing.querySelector("input");
const options = typing.querySelector("datalist");
const stateName = root.querySelector(".state-name");
const words = root.querySelector(".words");

const tapes = {};
let story = "terminal";
let state = null;
let history = [];
let busy = false;

async function tape(name) {
	tapes[name] ??= fetch(`media/contrail/${name}/tape.json`).then((response) => response.json());
	return tapes[name];
}

const url = (path) => `media/contrail/${story}/${path}`;

function play(path) {
	return new Promise((resolve) => {
		clip.src = url(path);
		clip.onplaying = () => screen.classList.add("playing");
		clip.onended = resolve;
		clip.onerror = resolve;
		clip.play().catch(resolve);
	});
}

async function rest(name) {
	const scene = (await tape(story)).scenes[name];
	state = name;
	key.src = url(scene.key);
	key.alt = scene.words.join(". ");
	await key.decode().catch(() => {});
	screen.classList.remove("playing");

	hotspots.replaceChildren(...scene.hotspots.map((spot) => {
		const button = document.createElement("button");
		button.className = "hotspot";
		button.style.cssText = `left:${spot.box.x * 100}%;top:${spot.box.y * 100}%;` +
			`width:${spot.box.w * 100}%;height:${spot.box.h * 100}%`;
		button.setAttribute("aria-label", spot.label);
		button.dataset.label = spot.label;
		button.onpointerenter = button.onfocus = () => prefetch(spot.move);
		button.onclick = () => press(spot.move);
		return button;
	}));

	typing.hidden = !scene.search;
	if (scene.search) {
		typed.placeholder = scene.search.bar;
		options.replaceChildren(...scene.search.options.map((option) => new Option(option.label)));
	}
	stateName.textContent = name;
	words.replaceChildren(...scene.words.map((line) => Object.assign(document.createElement("li"), { textContent: line })));
	back.disabled = history.length === 0;
	busy = false;
}

async function prefetch(move) {
	const entry = (await tape(story)).moves[move];
	if (!entry || document.head.querySelector(`link[href="${url(entry.clip)}"]`)) return;
	document.head.append(Object.assign(document.createElement("link"), { rel: "prefetch", href: url(entry.clip) }));
}

async function press(move) {
	if (busy) return;
	busy = true;
	const entry = (await tape(story)).moves[move];
	hotspots.replaceChildren();
	history.push({ from: state, move });
	await play(entry.clip);
	await rest(entry.lands);
}

back.onclick = async () => {
	if (busy || history.length === 0) return;
	busy = true;
	const { from, move } = history.pop();
	hotspots.replaceChildren();
	await play((await tape(story)).moves[move].back);
	await rest(from);
};

async function open() {
	busy = true;
	history = [];
	start.hidden = true;
	hotspots.replaceChildren();
	const opening = (await tape(story)).opening;
	await play(opening.clip);
	await rest(opening.lands);
}

start.onclick = open;
restart.onclick = () => { if (!busy) open(); };

showHotspots.onclick = () => {
	const on = showHotspots.getAttribute("aria-pressed") !== "true";
	showHotspots.setAttribute("aria-pressed", String(on));
	screen.classList.toggle("show-hotspots", on);
};

for (const button of root.querySelectorAll("[data-story]")) {
	button.onclick = async () => {
		if (busy || button.dataset.story === story) return;
		story = button.dataset.story;
		for (const other of root.querySelectorAll("[data-story]")) {
			other.setAttribute("aria-pressed", String(other === button));
		}
		root.dataset.story = story;
		if (state) await rest(state);
		else key.src = url("keys/home.webp");
	};
}

// Typing picks one of the search's options by its words, its city, or its code, as the platform's text sheet does.
typing.onsubmit = async (event) => {
	event.preventDefault();
	const search = (await tape(story)).scenes[state].search;
	const text = typed.value.trim().toLowerCase();
	const option = search.options.find((option) => {
		const [, city, code] = option.label.match(/^(.*) \((\w+)\)$/) ?? [];
		return [option.label, city, code].some((name) => name?.toLowerCase() === text);
	});
	typed.value = "";
	await press(option ? option.move : search.no_match.move);
};

key.src = url("keys/home.webp");
tape(story);
