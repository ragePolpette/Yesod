// Pi tool_call gate -> same contract as the Hermes hook (contract/risk.json). Unknown tools fail closed.
import { appendFileSync, readFileSync } from "node:fs";
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
	if (action === "allow_if_test_target" && isTestTarget(String(args?.url ?? ""))) return undefined;
	return `blocked: ${name} is ${cls}; not allowed in phase '${risk.phase}' (requires confirmation)`;
}

// Origin match, not a string prefix: "http://localhost.evil.example" must not match "http://localhost".
function isTestTarget(url: string): boolean {
	try {
		const u = new URL(url);
		return risk.test_targets.some((t: string) => {
			const o = new URL(t);
			return o.protocol === u.protocol && o.hostname === u.hostname && (o.port === "" || o.port === u.port);
		});
	} catch {
		return false;
	}
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event) => {
		const reason = decide(event.toolName, (event as any).input);
		if (!reason) return;
		if (process.env.SPIKE_GATE_LOG) appendFileSync(process.env.SPIKE_GATE_LOG, JSON.stringify({ tool: event.toolName, reason }) + "\n");
		return { block: true, reason };
	});
}
