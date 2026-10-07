// Option C: Level 1 loop in .NET with Microsoft.Extensions.AI (IChatClient + UseFunctionInvocation)
// and the official MCP C# SDK as client of the same adapter server. No agent harness.
// In production this is a class inside the .NET service; here it is a console app so the
// Python runner can drive it like the other two harnesses.
using System.ClientModel;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using OpenAI;

var opt = Args.Parse(args);
var sw = Stopwatch.StartNew();
var risk = JsonNode.Parse(File.ReadAllText(opt["risk"]))!;

await using var mcp = await McpClient.CreateAsync(new StdioClientTransport(new StdioClientTransportOptions
{
    Name = "spike",
    // SDK 2.2.0 waits ShutdownTimeout and then kills the stdio server at dispose (it does not exit on its own).
    // Irrelevant in the service, where the MCP client lives as long as the process; capped here for the spike.
    ShutdownTimeout = TimeSpan.FromMilliseconds(300),
    Command = opt["mcp-command"],
    Arguments = JsonSerializer.Deserialize<string[]>(opt["mcp-args"])!,
    EnvironmentVariables = JsonSerializer.Deserialize<Dictionary<string, string?>>(opt["mcp-env"])!,
}));
var tools = (await mcp.ListToolsAsync()).Select(t => (AITool)new GatedFunction(t, risk)).ToList();

var counter = new CountingChatClient(
    new OpenAIClient(new ApiKeyCredential(Environment.GetEnvironmentVariable("SPIKE_API_KEY") ?? "none"),
                     new OpenAIClientOptions { Endpoint = new Uri(opt["base-url"]) })
        .GetChatClient(opt["model"]).AsIChatClient());
var client = new ChatClientBuilder(counter)
    .UseFunctionInvocation(configure: f => f.MaximumIterationsPerRequest = 10)
    .Build();

var response = await client.GetResponseAsync(
    [new ChatMessage(ChatRole.User, File.ReadAllText(opt["prompt-file"]))],
    new ChatOptions { Tools = tools });

Console.WriteLine(JsonSerializer.Serialize(new
{
    final = response.Text,
    usage = new { input = counter.Input, output = counter.Output, requests = counter.Requests },
    inproc_ms = sw.ElapsedMilliseconds,
}));

// Gate: same contract as the Pi extension and the Hermes hook. Blocked calls return the reason to the
// model as the tool result; unknown tools and gate errors are blocked (fail closed).
sealed class GatedFunction(McpClientTool inner, JsonNode risk) : DelegatingAIFunction(inner)
{
    protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken ct)
    {
        string? reason;
        try { reason = Decide(Name, arguments.TryGetValue("url", out var u) ? u?.ToString() : null); }
        catch (Exception ex) { reason = $"blocked: gate error {ex.GetType().Name} (fail closed)"; }
        if (reason is null) return await base.InvokeCoreAsync(arguments, ct);
        if (Environment.GetEnvironmentVariable("SPIKE_GATE_LOG") is { } log)
            File.AppendAllText(log, JsonSerializer.Serialize(new { tool = Name, reason }) + "\n");
        return reason;
    }

    string? Decide(string tool, string? url)
    {
        var cls = risk["tools"]?[tool]?.GetValue<string>();
        if (cls is null) return $"blocked: {tool} is not in the risk contract (fail closed)";
        var phase = risk["phase"]!.GetValue<string>();
        var action = risk["policy"]?[phase]?[cls]?.GetValue<string>() ?? "block";
        if (action == "allow") return null;
        if (action == "allow_if_test_target" && IsTestTarget(url)) return null;
        return $"blocked: {tool} is {cls}; not allowed in phase '{phase}' (requires confirmation)";
    }

    bool IsTestTarget(string? url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var u) &&
        risk["test_targets"]!.AsArray().Any(t => Uri.TryCreate(t!.GetValue<string>(), UriKind.Absolute, out var o)
            && o.Scheme == u.Scheme && o.Host == u.Host && (o.IsDefaultPort || o.Port == u.Port));
}

// Sits below the function-invoking client, so it sees every model request of the loop.
sealed class CountingChatClient(IChatClient inner) : DelegatingChatClient(inner)
{
    public long Input, Output, Requests;

    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken ct = default)
    {
        var r = await base.GetResponseAsync(messages, options, ct);
        Requests++;
        Input += r.Usage?.InputTokenCount ?? 0;
        Output += r.Usage?.OutputTokenCount ?? 0;
        return r;
    }
}

static class Args
{
    public static Dictionary<string, string> Parse(string[] a) =>
        Enumerable.Range(0, a.Length / 2).ToDictionary(i => a[2 * i].TrimStart('-'), i => a[2 * i + 1]);
}
