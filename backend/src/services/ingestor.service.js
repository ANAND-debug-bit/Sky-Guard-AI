const config = require("../configs/index")


const processData = async (data) => {
    console.log(data)
}


const startIngestion = async () => {
    const streamUrl = `${config.sensorSimUrl}/v1/sensor/injected/HYD001`
    const response = await fetch(streamUrl)

    if (!response.ok) {
        throw new Error(`Stream connection failed: ${response.status} ${response.statusText}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder("utf-8")
    let buffer = ""

    while (true) {
        const { value, done } = await reader.read()

        if (done) break

        // Append the new chunk to whatever was left from the previous read
        buffer += decoder.decode(value, { stream: true })

        // Split on newlines — every complete line is one JSON record
        const lines = buffer.split("\n")

        // The last element may be an incomplete line; keep it for next iteration
        buffer = lines.pop()
        console.log("buffer before loop" + buffer.length)
        for (const line of lines) {
            console.log("buffer in loop" + buffer.length)
            const trimmed = line.trim()
            if (!trimmed) continue              // skip empty lines
            try {
                const data = JSON.parse(trimmed)
                processData(data)
            } catch {
                console.warn("[ingestor] skipped malformed JSON line:", trimmed)
            }
        }
    }
}

module.exports = { startIngestion }