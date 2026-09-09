// SPDX-License-Identifier: Apache-2.0
package main

import (
	"log"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

func main() {
	chaincode, err := contractapi.NewChaincode(&OliveChainContract{})
	if err != nil {
		log.Panicf("create OliveChain chaincode: %v", err)
	}
	if err := chaincode.Start(); err != nil {
		log.Panicf("start OliveChain chaincode: %v", err)
	}
}
