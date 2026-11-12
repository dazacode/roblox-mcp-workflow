--!nocheck
--[[
	ForgeKit.Probe - bounded, READ-ONLY scene diagnostics that return compact JSON.

	require(game.ServerStorage._Forge.Probe).scan({ root = "Workspace.Torii" })
	require(game.ServerStorage._Forge.Probe).compare("Workspace.Torii", manifestTable)
	require(game.ServerStorage._Forge.Probe).shots("Workspace.Torii")      -- exact screen_capture args

Designed for HUGE places (a real project here has ~350k instances): every entry point is
scoped to one root and hard-capped, never walks the whole DataModel by default, and
returns grouped findings {sev, code, count, examples, msg, fix} instead of one line per part.
]]
local HttpService = game:GetService("HttpService")

local Probe = {}

local STUDS_PER_M = 1 / 0.28
local GREY = Color3.new(0.639, 0.635, 0.647) -- importer's default when a colour is dropped

local function resolve(root)
	if typeof(root) == "Instance" then
		return root
	end
	local cur = game
	for part in string.gmatch(tostring(root), "[^%.]+") do
		if not (cur == game and part == "game") then
			cur = cur:FindFirstChild(part)
			if not cur then
				return nil
			end
		end
	end
	return cur
end

local function round(n, d)
	local m = 10 ^ (d or 2)
	return math.floor(n * m + 0.5) / m
end

local function v3(v)
	return { round(v.X), round(v.Y), round(v.Z) }
end

local function hex(c)
	return string.format("#%02x%02x%02x", math.floor(c.R * 255 + 0.5), math.floor(c.G * 255 + 0.5), math.floor(c.B * 255 + 0.5))
end

local function near(a, b, tol)
	return math.abs(a.R - b.R) < tol and math.abs(a.G - b.G) < tol and math.abs(a.B - b.B) < tol
end

local function pathOf(i)
	return i:GetFullName()
end

-- Findings collector: groups by code, keeps 3 examples, counts the rest.
local function newFindings()
	local byCode, order = {}, {}
	return {
		add = function(sev, code, inst, msg, fix)
			local f = byCode[code]
			if not f then
				f = { sev = sev, code = code, count = 0, examples = {}, msg = msg, fix = fix }
				byCode[code] = f
				table.insert(order, f)
			end
			f.count += 1
			if #f.examples < 3 and inst then
				table.insert(f.examples, pathOf(inst))
			end
		end,
		list = function()
			return order
		end,
	}
end

-- World-space AABB of a set of parts (true corners, so rotated parts aren't overstated by bounding boxes).
local function worldAabb(parts)
	local mn = Vector3.new(math.huge, math.huge, math.huge)
	local mx = -mn
	for _, p in ipairs(parts) do
		local h = p.Size / 2
		for sx = -1, 1, 2 do
			for sy = -1, 1, 2 do
				for sz = -1, 1, 2 do
					local w = p.CFrame:PointToWorldSpace(Vector3.new(h.X * sx, h.Y * sy, h.Z * sz))
					mn = Vector3.new(math.min(mn.X, w.X), math.min(mn.Y, w.Y), math.min(mn.Z, w.Z))
					mx = Vector3.new(math.max(mx.X, w.X), math.max(mx.Y, w.Y), math.max(mx.Z, w.Z))
				end
			end
		end
	end
	return mn, mx
end

--[[ scan(cfg)
	cfg.root            string path or Instance (required)
	cfg.maxDescendants  default 20000 - refuses bigger roots instead of freezing Studio
	cfg.maxParts        default 4000  - parts analysed in detail
	cfg.expectAnchored  default true  - imported/static assets should be anchored
	cfg.ground          default true  - raycast down to detect floating
]]
function Probe.scan(cfg)
	cfg = cfg or {}
	local root = resolve(cfg.root)
	if not root then
		return HttpService:JSONEncode({ ok = false, code = "ROOT_NOT_FOUND", root = tostring(cfg.root), hint = "check the path with search_game_tree" })
	end
	local maxDesc, maxParts = cfg.maxDescendants or 20000, cfg.maxParts or 4000
	local t0 = os.clock()
	local desc = root:GetDescendants()
	if #desc > maxDesc then
		return HttpService:JSONEncode({
			ok = false,
			code = "TOO_BIG",
			descendants = #desc,
			limit = maxDesc,
			hint = "scope to a smaller sub-model, or raise maxDescendants deliberately (large scans can freeze Studio)",
		})
	end

	local F = newFindings()
	local classes, parts, scripts, meshParts, textured = {}, {}, 0, 0, 0
	local noCollide, unanchored = 0, 0
	for _, d in ipairs(desc) do
		classes[d.ClassName] = (classes[d.ClassName] or 0) + 1
		if d:IsA("BaseScript") then
			scripts += 1
		end
		if d:IsA("BasePart") and #parts < maxParts then
			table.insert(parts, d)
		end
	end
	if root:IsA("BasePart") then
		table.insert(parts, 1, root)
	end

	for _, p in ipairs(parts) do
		local s = p.Size
		if s.X ~= s.X or s.Y ~= s.Y or s.Z ~= s.Z or s.Magnitude < 0.01 then
			F.add("error", "BAD_SIZE", p, "zero/NaN size part", "delete it or fix the source mesh")
		end
		if cfg.expectAnchored ~= false and not p.Anchored then
			unanchored += 1
			F.add("warn", "UNANCHORED", p, "part is not anchored (will fall/drift in play)", "set Anchored = true unless it should simulate")
		end
		if not p.CanCollide then
			noCollide += 1
		end
		if p:IsA("MeshPart") then
			meshParts += 1
			local sa = p:FindFirstChildWhichIsA("SurfaceAppearance")
			local hasTex = (sa and sa.ColorMap ~= "") or p.TextureID ~= ""
			if hasTex then
				textured += 1
			elseif near(p.Color, GREY, 0.012) then
				F.add("warn", "DEFAULT_GREY_MESH", p, "untextured MeshPart still has the importer's default grey", "set Color from the source material (manifest.materials[].base_color_hex)")
			end
			if p.MeshId == "" then
				F.add("error", "EMPTY_MESHID", p, "MeshPart has no MeshId (asset not loaded/moderated?)", "check the upload's moderationState")
			end
		end
	end
	if scripts > 0 then
		F.add("info", "SCRIPTS_INSIDE", nil, scripts .. " script(s) inside the scanned root", "static assets normally contain none")
	end
	if #parts > 0 and noCollide == #parts then
		F.add("info", "NO_COLLISION", nil, "every part has CanCollide=false", "enable collision on walkable/solid parts")
	end

	local mn, mx = worldAabb(parts)
	local size, center = mx - mn, (mx + mn) / 2
	local out = {
		ok = true,
		root = pathOf(root),
		descendants = #desc,
		classes = classes,
		parts = #parts,
		meshParts = meshParts,
		texturedMeshParts = textured,
		truncated = #parts >= maxParts,
		bbox = #parts > 0 and { size = v3(size), center = v3(center), min = v3(mn), max = v3(mx) } or nil,
	}

	if cfg.ground ~= false and #parts > 0 then
		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		params.FilterDescendantsInstances = { root }
		local origin = Vector3.new(center.X, mn.Y + 0.25, center.Z)
		local hit = workspace:Raycast(origin, Vector3.new(0, -500, 0), params)
		if hit then
			local gap = mn.Y - hit.Position.Y
			out.groundY = round(hit.Position.Y)
			out.gapToGround = round(gap)
			if gap > 0.75 then
				F.add("warn", "FLOATING", root, string.format("bottom is %.2f studs above the surface below", gap), "move Y down by the gap")
			end
		else
			out.groundY = nil
		end
		-- GetPartBoundsInBox takes OverlapParams (NOT RaycastParams) - different type, same fields
		local op = OverlapParams.new()
		op.FilterType = Enum.RaycastFilterType.Exclude
		op.FilterDescendantsInstances = { root }
		out.boundsOverlapCount = #workspace:GetPartBoundsInBox(CFrame.new(center), size, op) -- bounding-box test only; real overlap needs GetPartsInPart
	end

	local list = F.list()
	table.sort(list, function(a, b)
		local rank = { error = 1, warn = 2, info = 3 }
		return rank[a.sev] < rank[b.sev]
	end)
	out.findings = list
	out.ms = math.floor((os.clock() - t0) * 1000)
	return HttpService:JSONEncode(out)
end

--[[ compare(root, manifest) - diff Studio reality against the Blender manifest.
	Fixes the two things imports get wrong most: SCALE and COLOUR. Returns the exact ScaleTo factor. ]]
function Probe.compare(rootRef, manifest)
	local root = resolve(rootRef)
	if not root then
		return HttpService:JSONEncode({ ok = false, code = "ROOT_NOT_FOUND" })
	end
	local F = newFindings()
	local parts, meshes = {}, {}
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("BasePart") then
			table.insert(parts, d)
			if d:IsA("MeshPart") then
				table.insert(meshes, d)
			end
		end
	end
	local mn, mx = worldAabb(parts)
	local size = mx - mn
	local out = { ok = true, root = pathOf(root), measured_height_studs = round(size.Y), measured_size_studs = v3(size) }

	local expH = manifest.expected_height_studs
	if expH and size.Y > 0 then
		local factor = expH / size.Y
		out.expected_height_studs = expH
		out.scale_factor = round(factor, 4)
		if math.abs(factor - 1) > 0.05 then
			F.add("error", "SCALE_MISMATCH", root, string.format("height %.2f studs, expected %.2f", size.Y, expH),
				string.format("model:ScaleTo(model:GetScale() * %.4f)  (Model instances only; a lone MeshPart needs Size*factor)", factor))
		end
	end

	-- mesh presence by loose name match (importer nests/renames meshes)
	for _, m in ipairs(manifest.meshes or {}) do
		local found
		for _, mp in ipairs(meshes) do
			if string.find(string.lower(mp.Name), string.lower(m.name), 1, true) then
				found = mp
				break
			end
		end
		if not found then
			F.add("error", "MISSING_MESH", root, "no MeshPart matching '" .. m.name .. "'", "check TRI_BUDGET / upload moderation; names are matched loosely")
		else
			-- colour check against the material this mesh was exported with
			local matName = m.materials and m.materials[1]
			for _, mat in ipairs(manifest.materials or {}) do
				if mat.name == matName and mat.base_color_hex and not mat.has_color_texture then
					local want = Color3.fromHex(mat.base_color_hex)
					if not near(found.Color, want, 0.03) then
						F.add("warn", "COLOR_MISMATCH", found, string.format("Color %s, source %s", hex(found.Color), mat.base_color_hex),
							string.format("part.Color = Color3.fromHex(\"%s\")", mat.base_color_hex))
					end
				end
			end
		end
	end
	if manifest.meshes and #meshes ~= #manifest.meshes then
		F.add("info", "MESH_COUNT", root, string.format("%d MeshParts vs %d exported meshes", #meshes, #manifest.meshes), "importer may nest or split; confirm none are missing")
	end
	out.findings = F.list()
	return HttpService:JSONEncode(out)
end

--[[ shots(root) - exact camera args for screen_capture so verification is one call per view. ]]
function Probe.shots(rootRef, distanceMult)
	local root = resolve(rootRef)
	if not root then
		return HttpService:JSONEncode({ ok = false, code = "ROOT_NOT_FOUND" })
	end
	local parts = {}
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("BasePart") then
			table.insert(parts, d)
		end
	end
	if root:IsA("BasePart") then
		table.insert(parts, root)
	end
	local mn, mx = worldAabb(parts)
	local c, r = (mn + mx) / 2, (mx - mn).Magnitude * 0.5
	local d = r * (distanceMult or 2.2)
	local function cam(name, dir)
		return { name = name, camera_position = v3(c + dir.Unit * d), look_at_position = v3(c) }
	end
	return HttpService:JSONEncode({
		ok = true,
		center = v3(c),
		radius = round(r),
		shots = {
			cam("world -Z side", Vector3.new(0, 0.25, -1)),
			cam("world +X side", Vector3.new(1, 0.25, 0)),
			cam("world +Z side", Vector3.new(0, 0.25, 1)),
			cam("iso", Vector3.new(1, 0.8, -1)),
		},
	})
end

--[[ tree(root, depth) - compact outline: class counts per level, for orienting inside big places. ]]
function Probe.tree(rootRef, depth, limit)
	local root = resolve(rootRef)
	if not root then
		return HttpService:JSONEncode({ ok = false, code = "ROOT_NOT_FOUND" })
	end
	local lines, cap = {}, limit or 120
	local function walk(i, d)
		if #lines >= cap then
			return
		end
		local kids = i:GetChildren()
		table.insert(lines, string.rep("  ", d) .. i.Name .. " [" .. i.ClassName .. "] kids=" .. #kids)
		if d < (depth or 2) then
			for _, k in ipairs(kids) do
				walk(k, d + 1)
			end
		end
	end
	walk(root, 0)
	return HttpService:JSONEncode({ ok = true, truncated = #lines >= cap, lines = lines })
end

return Probe
