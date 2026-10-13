module "compute" {
    source = "./modules/compute"
    project = var.project
    zone = var.zone
    network = module.network.network
    service_account = module.iam.service_account
}
module "iam" {
  source = "./modules/iam"
  project = var.project
  owner_account = var.owner_account
}
module "network" {
  source = "./modules/network"
  project = var.project
  region = var.region
}
module "secrets" {
  source = "./modules/secrets"
  project = var.project
  service_account = module.iam.service_account
}
module "storage" {
  source = "./modules/storage"
  region = var.region
  service_account = module.iam.service_account
}