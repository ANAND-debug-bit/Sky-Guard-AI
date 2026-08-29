const express = require("express");
const connectDB = require("./configs/db")
const errorHandler = require("./middlewares/errorHandler.middleware")
const { startIngestion } = require("./services/ingestor.service")
const app = express();
connectDB()
startIngestion()
app.use(errorHandler);
module.exports = app;
