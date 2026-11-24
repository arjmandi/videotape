// The tests' clips play while they are on screen, and the screen test's tabs swap which model's keys show.

const clips = document.querySelectorAll(".test video");
const watcher = new IntersectionObserver((entries) => {
	for (const { target, isIntersecting } of entries) {
		if (isIntersecting) target.play().catch(() => {});
		else target.pause();
	}
}, { threshold: 0.4 });
if (!matchMedia("(prefers-reduced-motion: reduce)").matches) clips.forEach((clip) => watcher.observe(clip));
clips.forEach((clip) => { clip.controls = matchMedia("(prefers-reduced-motion: reduce)").matches; });

const tabs = document.querySelectorAll("[data-model]");
const keys = document.querySelectorAll(".screen-test img");

function show(model) {
	for (const tab of tabs) tab.setAttribute("aria-selected", String(tab.dataset.model === model));
	for (const key of keys) {
		const [story, name] = key.dataset.key.split("/");
		key.src = `media/screen-test/${model}/${story}/${name}.webp`;
		key.alt = `${model}'s take of ${name} in the ${story} story`;
	}
}

for (const tab of tabs) tab.onclick = () => show(tab.dataset.model);
show("gemini-omni-flash-1.2");
