local major, minor, revision, codename = love.getVersion()
local version = string.format(
    "LÖVE %d.%d.%d %s",
    major,
    minor,
    revision,
    codename or ""
)

print("makelove capability project")
print(version)

function love.draw()
    love.graphics.clear(0.08, 0.09, 0.11)
    love.graphics.setColor(0.9, 0.95, 1.0)
    love.graphics.print("makelove capability project", 24, 64)
    love.graphics.print(version, 24, 88)
end
