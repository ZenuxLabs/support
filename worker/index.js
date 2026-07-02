// Cloudflare Worker — serves support scripts at the operating instance's host
// Scripts are embedded at deploy time via wrangler (no KV needed).
// The scripts themselves contain NO secrets — auth keys are always passed at runtime.

const SCRIPTS = {
  "join.ps1": `{{JOIN_PS1}}`,
  "crash-check.ps1": `{{CRASH_CHECK_PS1}}`,
  "customer-ssh-bootstrap.ps1": `{{CUSTOMER_SSH_BOOTSTRAP_PS1}}`,
  "windows-ssh-onboard.ps1": `{{WINDOWS_SSH_ONBOARD_PS1}}`,
  "windows-ssh-offboard.ps1": `{{WINDOWS_SSH_OFFBOARD_PS1}}`,
  "run-verified.ps1": `{{RUN_VERIFIED_PS1}}`,
};

const ARTIFACT_VERSION = "{{ARTIFACT_VERSION}}";
const SCRIPT_MANIFEST_JSON = `{{SCRIPT_MANIFEST_JSON}}`;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/+/, "").replace(/\/+$/, "");

    if (path === "") {
      return new Response(
        [
          "ZenuxLabs Support Fabric",
          "",
          "One-command Windows fleet onboarding (elevated PowerShell):",
          "  irm " + url.origin + "/join.ps1 | iex",
          "",
          "Manifest:",
          "  /manifest.json",
          "",
          "Verified runner:",
          "  /run-verified.ps1",
          "",
          "Scripts:",
          "  /join.ps1",
          "  /crash-check.ps1",
          "  /customer-ssh-bootstrap.ps1",
          "  /windows-ssh-onboard.ps1",
          "  /windows-ssh-offboard.ps1",
          "",
          `Versioned scripts: /v/${ARTIFACT_VERSION}/<script-name>`,
          "",
        ].join("\n"),
        { headers: { "Content-Type": "text/plain; charset=utf-8" } }
      );
    }

    if (path === "manifest.json") {
      return new Response(SCRIPT_MANIFEST_JSON, {
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=300",
        },
      });
    }

    if (path === "onboard.ps1") {
      return new Response(
        "Gone: use /customer-ssh-bootstrap.ps1 for production Windows SSH onboarding.\n",
        {
          status: 410,
          headers: { "Content-Type": "text/plain; charset=utf-8" },
        }
      );
    }

    const versionPrefix = `v/${ARTIFACT_VERSION}/`;
    const scriptName = path.startsWith(versionPrefix)
      ? path.slice(versionPrefix.length)
      : path;
    const script = SCRIPTS[scriptName];
    if (!script) {
      return new Response("Not Found", { status: 404 });
    }

    const cacheControl = path.startsWith(versionPrefix)
      ? "public, max-age=86400, immutable"
      : "public, max-age=300";

    return new Response(script, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": cacheControl,
      },
    });
  },
};
