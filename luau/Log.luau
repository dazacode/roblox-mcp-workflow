--!nocheck
--[[
	ForgeKit.Log - turns the raw Output stream into something an AI can reason about.

	Log.digest({ sinceSeconds = 120 })  -> grouped, de-duplicated errors/warnings with script+line
	Log.emit("info", "inventory", { items = 3 })   -> prints  [FORGE] {"l":"info","t":"inventory","d":{...}}
	Log.events("inventory")                        -> decoded [FORGE] events from the log history

	Works per DataModel: call it in Server and in Client separately during a playtest.
	Reads LogService history, so nothing has to be installed *before* the bug happens.
]]
local HttpService = game:GetService("HttpService")
local LogService = game:GetService("LogService")

local Log = {}

function Log.emit(level, tag, data)
	print("[FORGE] " .. HttpService:JSONEncode({ l = level, t = tag, d = data, c = math.floor(os.clock() * 1000) }))
end

local function typeName(t)
	if t == Enum.MessageType.MessageError then
		return "error"
	elseif t == Enum.MessageType.MessageWarning then
		return "warn"
	elseif t == Enum.MessageType.MessageInfo then
		return "info"
	end
	return "out"
end

-- "ServerScriptService.Foo:12: attempt to index nil with 'bar'"  ->  script, line, message
local function parseError(msg)
	local script, line, rest = string.match(msg, "^([%w_%.%[%]%s%-]+):(%d+): (.*)$")
	if script then
		return script, tonumber(line), rest
	end
	local s2, l2 = string.match(msg, "Script '([^']+)', Line (%d+)")
	if s2 then
		return s2, tonumber(l2), msg
	end
	return nil, nil, msg
end

local function normalise(msg)
	-- collapse hex/asset ids and any 3+ digit run so "rbxassetid://123" and "rbxassetid://456" group together
	return (string.gsub(string.gsub(msg, "0x%x+", "0x"), "%d%d%d+", "#"))
end

-- Known Roblox failure shapes -> stable code + the usual fix. Lets an AI branch on `code`, not prose.
local RULES = {
	{ "ContentId: .+ failed", "ASSET_LOAD_FAIL", "asset id missing, not approved by moderation, wrong asset type, or not owned/shared with this experience" },
	{ "attempt to index nil", "NIL_INDEX", "a value is nil: guard it, or WaitForChild / check the replication timing" },
	{ "attempt to call a nil value", "NIL_CALL", "method/function name typo or module not returning it" },
	{ "is not a valid member of", "BAD_MEMBER", "wrong child/property name, or instance not replicated yet (use WaitForChild)" },
	{ "Infinite yield possible", "INFINITE_YIELD", "WaitForChild target never appears: wrong name/path or never created" },
	{ "Http requests are not enabled", "HTTP_DISABLED", "enable HttpService.HttpEnabled (Game Settings > Security) and allowlist the domain" },
	{ "HTTP 403", "HTTP_FORBIDDEN", "scope/permission missing for this Open Cloud or HTTP call" },
	{ "Stack Begin", "STACK_TRACE", "see script+line" },
	{ "DataStore request was added to queue", "DATASTORE_THROTTLE", "too many DataStore calls; batch/cache and respect budgets" },
	{ "Attempt to set .+ is not allowed", "SECURITY_BLOCKED", "property is restricted in this context (plugin/server/client)" },
}

local function classify(msg)
	for _, r in ipairs(RULES) do
		if string.find(msg, r[1]) then
			return r[2], r[3]
		end
	end
	return nil, nil
end

function Log.digest(opts)
	opts = opts or {}
	local since = os.time() - (opts.sinceSeconds or 300)
	local history = LogService:GetLogHistory()
	local groups, order, counts = {}, {}, { error = 0, warn = 0, info = 0, out = 0 }
	for _, e in ipairs(history) do
		if e.timestamp >= since then
			local kind = typeName(e.messageType)
			counts[kind] += 1
			if kind == "error" or kind == "warn" then
				local script, line, msg = parseError(e.message)
				local key = kind .. "|" .. (script or "?") .. "|" .. normalise(msg)
				local g = groups[key]
				if not g then
					local code, fix = classify(msg)
					g = { kind = kind, code = code, fix = fix, script = script, line = line, message = string.sub(msg, 1, 300), count = 0, first = e.timestamp, last = e.timestamp, sample = nil }
					groups[key] = g
					table.insert(order, g)
				end
				g.count += 1
				g.last = e.timestamp
			end
		end
	end
	table.sort(order, function(a, b)
		if a.kind ~= b.kind then
			return a.kind == "error"
		end
		return a.count > b.count
	end)
	local top = {}
	for i = 1, math.min(#order, opts.max or 15) do
		top[i] = order[i]
	end
	return HttpService:JSONEncode({
		ok = true,
		window_s = opts.sinceSeconds or 300,
		totals = counts,
		distinct = #order,
		groups = top,
		verdict = counts.error == 0 and "clean" or "errors",
	})
end

function Log.events(tag, sinceSeconds)
	local since = os.time() - (sinceSeconds or 300)
	local out = {}
	for _, e in ipairs(LogService:GetLogHistory()) do
		if e.timestamp >= since then
			local json = string.match(e.message, "^%[FORGE%] (.*)$")
			if json then
				local ok, ev = pcall(HttpService.JSONDecode, HttpService, json)
				if ok and (not tag or ev.t == tag) then
					table.insert(out, ev)
				end
			end
		end
	end
	return HttpService:JSONEncode({ ok = true, count = #out, events = out })
end

return Log
