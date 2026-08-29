const mongoose = require("mongoose");
const config = require("./index")
const connectDB = async () => {
    try {
        const connection = await mongoose.connect(config.MONGO_URI)
        console.log(`DB Connected to ${connection.connection.host}`)
    }
    catch (err) {
        console.log(err.message)
    }
}

module.exports = connectDB