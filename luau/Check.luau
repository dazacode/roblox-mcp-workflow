--!nocheck
--[[
	ForgeKit.Check - tiny assertion runner whose output is JSON an AI can act on.

	local C = require(game.ServerStorage._Forge.Check)
	return C.run({
		{ "spawn exists",   function() C.truthy(workspace:FindFirstChildWhichIsA("SpawnLocation"), "no SpawnLocation") end },
		{ "gravity sane",   function() C.near(workspace.Gravity, 196.2, 0.5) end },
	})
	-- -> {"passed":2,"failed":0,"results":[{"name":"spawn exists","ok":true,"ms":0}, ...]}

	Run in the Server and Client datamodels separately during a playtest.
	For real ModuleScript unit tests prefer Roblox's rbx-unit-test skill; this is for fast ad-hoc assertions.
]]
local HttpService = game:GetService("HttpService")

local Check = {}

function Check.truthy(v, msg)
	if not v then
		error(msg or "expected truthy, got " .. tostring(v), 2)
	end
end

function Check.eq(a, b, msg)
	if a ~= b then
		error(string.format("%s: expected %s, got %s", msg or "eq", tostring(b), tostring(a)), 2)
	end
end

function Check.near(a, b, eps, msg)
	if math.abs(a - b) > (eps or 1e-3) then
		error(string.format("%s: expected %s +/- %s, got %s", msg or "near", tostring(b), tostring(eps), tostring(a)), 2)
	end
end

function Check.exists(path, className)
	local cur = game
	for part in string.gmatch(path, "[^%.]+") do
		cur = cur and cur:FindFirstChild(part)
	end
	if not cur then
		error("missing instance: " .. path, 2)
	end
	if className and not cur:IsA(className) then
		error(string.format("%s is %s, expected %s", path, cur.ClassName, className), 2)
	end
	return cur
end

function Check.run(tests)
	local results, passed = {}, 0
	for _, t in ipairs(tests) do
		local name, fn = t[1], t[2]
		local t0 = os.clock()
		local ok, err = xpcall(fn, function(e)
			return { msg = tostring(e), trace = string.sub(debug.traceback("", 2), 1, 400) }
		end)
		if ok then
			passed += 1
			table.insert(results, { name = name, ok = true, ms = math.floor((os.clock() - t0) * 1000) })
		else
			table.insert(results, { name = name, ok = false, error = err.msg, trace = err.trace })
		end
	end
	return HttpService:JSONEncode({ passed = passed, failed = #tests - passed, total = #tests, results = results })
end

return Check
