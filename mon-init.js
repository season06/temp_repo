print("=== Mongo Init Script ===");

db = db.getSiblingDB("isop_defense");
db.createCollection("event_trigger");
db.collection.insertOne({
    name: 'test'
})

print("=== Mongo Init Script Finished ===");