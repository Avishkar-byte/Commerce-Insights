// Creates the pipeline and dashboard users.
//
// Runs only on the first start of an empty mongo-data volume, executed by the
// mongo image's entrypoint as the root user. Passwords are read from the
// environment so they never appear in this file or in the image.

const dbName = process.env.MONGO_DB;
const pipelinePassword = process.env.OLIST_PIPELINE_PASSWORD;
const dashboardPassword = process.env.OLIST_DASHBOARD_PASSWORD;

if (!dbName || !pipelinePassword || !dashboardPassword) {
  throw new Error(
    "MONGO_DB, OLIST_PIPELINE_PASSWORD and OLIST_DASHBOARD_PASSWORD must all be set."
  );
}

const target = db.getSiblingDB(dbName);

target.createUser({
  user: "olist_pipeline",
  pwd: pipelinePassword,
  roles: [{ role: "readWrite", db: dbName }],
});

target.createUser({
  user: "olist_dashboard",
  pwd: dashboardPassword,
  roles: [{ role: "read", db: dbName }],
});

print("Created users olist_pipeline (readWrite) and olist_dashboard (read) on " + dbName);
