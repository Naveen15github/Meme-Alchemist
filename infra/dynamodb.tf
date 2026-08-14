# Single table. `id` is the meme uuid; the GSI puts every meme in one
# partition keyed by a constant so the gallery can read them back sorted by
# createdAt without a scan. Fine at demo scale, and the access pattern is
# explicit rather than accidental.
resource "aws_dynamodb_table" "memes" {
  name         = "${local.name}-memes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "gsiBucket"
    type = "S"
  }

  attribute {
    name = "createdAt"
    type = "S"
  }

  global_secondary_index {
    name            = "byCreatedAt"
    hash_key        = "gsiBucket"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = false # demo workload; regenerating a meme is cheaper than PITR
  }
}
