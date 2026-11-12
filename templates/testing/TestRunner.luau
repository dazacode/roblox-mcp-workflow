--!nocheck
--[[
	Runs every *.spec ModuleScript under ReplicatedStorage.Tests with Jest and returns ONE JSON string.
	Call:  return require(game.ServerScriptService.TestRunner).run()
	The JSON is built for an AI to read: totals, per-file pass/fail, and failure messages (not Jest's console art).
]]
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local TestRunner = {}

function TestRunner.run()
	local Jest = require(ReplicatedStorage.DevPackages.Jest)
	local started = os.clock()
	local status, result = Jest.runCLI(
		ReplicatedStorage.Tests,
		{ verbose = false, ci = true },
		{ ReplicatedStorage.Tests }
	)
		:awaitStatus()
	if status ~= "Resolved" then
		return HttpService:JSONEncode({ ok = false, stage = "runCLI", status = status, error = tostring(result) })
	end
	local results = result.results
	local files, failures = {}, {}
	for _, tr in ipairs(results.testResults) do
		local name = tostring(tr.testFilePath)
		table.insert(files, {
			file = name,
			passed = tr.numPassingTests,
			failed = tr.numFailingTests,
			skipped = tr.numPendingTests,
		})
		for _, a in ipairs(tr.testResults) do
			if a.status == "failed" then
				table.insert(failures, {
					file = name,
					test = a.fullName,
					message = string.sub(table.concat(a.failureMessages or {}, "\n"), 1, 600),
				})
			end
		end
		if tr.failureMessage and tr.numFailingTests == 0 then
			table.insert(
				failures,
				{ file = name, test = "<suite failed to run>", message = string.sub(tr.failureMessage, 1, 600) }
			)
		end
	end
	return HttpService:JSONEncode({
		ok = results.success and #failures == 0,
		passed = results.numPassedTests,
		failed = results.numFailedTests,
		suites = results.numTotalTestSuites,
		suitesFailed = results.numFailedTestSuites,
		seconds = math.floor((os.clock() - started) * 100) / 100,
		files = files,
		failures = failures,
	})
end

return TestRunner
