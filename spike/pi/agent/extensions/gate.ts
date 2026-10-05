// Pi tool_call gate -> same contract as the Hermes hook (contract/risk.json). Unknown tools fail closed.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const here = dirname(fileURLToPath(import.meta.url));
const risk = JSON.parse(readFileSync(process.env.SPIKE_RISK ?? join(here, "../../../contract/risk.json"), "utf8"));

function decide(toolName: string, args: any): string | undefined {
	const name = toolName.replace(/^mcp__.+?__/, "");
	const cls = risk.tools[name];
	if (!cls) return `blocked: ${toolName} is not in the risk contract (fail closed)`;
	const action = risk.policy[risk.phase][cls] ?? "block";
	if (action === "allow") return undefined;
	if (action === "allow_if_test_target" && risk.test_targets.some((p: string) => String(args?.url ?? "").startsWith(p))) return undefined;
	return `blocked: ${name} is ${cls}; not allowed in phase '${risk.phase}' (requires confirmation)`;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event) => {
		const reason = decide(event.toolName, (event as any).input);
		if (reason) return { block: true, reason };
	});
}
