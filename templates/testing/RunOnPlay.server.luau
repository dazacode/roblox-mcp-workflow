--!nocheck
-- In Play mode, run the suite automatically and print one machine-readable line.
local RunService = game:GetService("RunService")
if not RunService:IsRunning() then
	return
end
local ok, out = pcall(function()
	return require(script.Parent.TestRunner).run()
end)
print(
	"[TESTS] " .. (ok and out or ('{"ok":false,"stage":"runner","error":' .. string.format("%q", tostring(out)) .. "}"))
)
