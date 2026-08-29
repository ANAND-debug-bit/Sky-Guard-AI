const config = require("../configs/index")
const errorHandler = (err, req, res, next) => {
    const response = {
        statusCode: err.statusCode || 500,
        message: err.message || "Internal Server Error",
        success: false,
    }
    if (config.NODE_ENV === "development") {
        response.stack = err.stack
    }
    response.errors = err.errors || []
    return res.status(response.statusCode).json(response)
}

module.exports = errorHandler 