output "bootstrap_brokers_tls" {
  description = "TLS bootstrap broker connection string. The app's KAFKA_BOOTSTRAP_SERVERS should be set to this when enable_kafka = true."
  value       = aws_msk_cluster.main.bootstrap_brokers_tls
}

output "cluster_arn" {
  value = aws_msk_cluster.main.arn
}
